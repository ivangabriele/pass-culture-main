import datetime
import logging
import os

import sqlalchemy as sqla
import sqlalchemy.orm as sa_orm
from flask import request
from flask_login import current_user
from flask_login import login_required
from openai import OpenAI
from werkzeug.exceptions import NotFound

import pcapi.core.offerers.api as offerers_api
import pcapi.core.offers.api as offers_api
import pcapi.core.offers.repository as offers_repository
from pcapi import settings
from pcapi.core.categories import pro_categories
from pcapi.core.categories import subcategories
from pcapi.core.offerers import exceptions as offerers_exceptions
from pcapi.core.offerers import models as offerers_models
from pcapi.core.offerers import repository as offerers_repository
from pcapi.core.offers import exceptions
from pcapi.core.offers import models
from pcapi.core.offers import schemas as offers_schemas
from pcapi.core.offers import validation
from pcapi.core.providers.constants import TITELIVE_MUSIC_TYPES
from pcapi.core.reminders.external import reminders_notifications
from pcapi.models import api_errors
from pcapi.models import db
from pcapi.models.feature import FeatureToggle
from pcapi.repository.session_management import atomic
from pcapi.routes.apis import private_api
from pcapi.routes.serialization import offers_serialize
from pcapi.routes.serialization.thumbnails_serialize import CreateThumbnailBodyModel
from pcapi.routes.serialization.thumbnails_serialize import CreateThumbnailResponseModel
from pcapi.serialization.decorator import spectree_serialize
from pcapi.utils import rest
from pcapi.workers.update_all_offers_active_status_job import update_all_offers_active_status_job

from . import blueprint


logger = logging.getLogger(__name__)


@private_api.route("/offers", methods=["GET"])
@login_required
@spectree_serialize(
    response_model=offers_serialize.ListOffersResponseModel,
    api=blueprint.pro_private_schema,
)
@atomic()
def list_offers(query: offers_serialize.ListOffersQueryModel) -> offers_serialize.ListOffersResponseModel:
    paginated_offers = offers_repository.get_capped_offers_for_filters(
        user_id=current_user.id,
        user_is_admin=current_user.has_admin_role,
        offers_limit=offers_api.OFFERS_RECAP_LIMIT,
        offerer_id=query.offerer_id,
        status=query.status.value if query.status else None,
        venue_id=query.venue_id,
        category_id=query.categoryId,
        name_keywords_or_ean=query.name_or_ean,
        creation_mode=query.creation_mode,
        period_beginning_date=query.period_beginning_date,
        period_ending_date=query.period_ending_date,
        offerer_address_id=query.offerer_address_id,
    )

    return offers_serialize.ListOffersResponseModel(__root__=offers_serialize.serialize_capped_offers(paginated_offers))


@private_api.route("/offers/<int:offer_id>", methods=["GET"])
@login_required
@spectree_serialize(
    response_model=offers_serialize.GetIndividualOfferWithAddressResponseModel,
    api=blueprint.pro_private_schema,
)
@atomic()
def get_offer(offer_id: int) -> offers_serialize.GetIndividualOfferWithAddressResponseModel:
    load_all: offers_repository.OFFER_LOAD_OPTIONS = [
        "mediations",
        "product",
        "price_category",
        "venue",
        "bookings_count",
        "offerer_address",
        "future_offer",
        "pending_bookings",
        "headline_offer",
        "event_opening_hours",
    ]
    try:
        offer = offers_repository.get_offer_by_id(offer_id, load_options=load_all)
    except exceptions.OfferNotFound:
        raise api_errors.ApiErrors(
            errors={
                "global": ["Aucun objet ne correspond à cet identifiant dans notre base de données"],
            },
            status_code=404,
        )
    rest.check_user_has_access_to_offerer(current_user, offer.venue.managingOffererId)

    return offers_serialize.GetIndividualOfferWithAddressResponseModel.from_orm(offer)


@private_api.route("/offers/<int:offer_id>/stocks/", methods=["GET"])
@login_required
@spectree_serialize(
    response_model=offers_serialize.GetStocksResponseModel,
    api=blueprint.pro_private_schema,
)
@atomic()
def get_stocks(offer_id: int, query: offers_serialize.StocksQueryModel) -> offers_serialize.GetStocksResponseModel:
    try:
        offer = offers_repository.get_offer_by_id(offer_id, load_options=["offerer_address"])
    except exceptions.OfferNotFound:
        raise api_errors.ApiErrors(
            errors={
                "global": ["Aucun objet ne correspond à cet identifiant dans notre base de données"],
            },
            status_code=404,
        )
    rest.check_user_has_access_to_offerer(current_user, offer.venue.managingOffererId)
    has_stocks = offers_repository.offer_has_stocks(offer_id=offer_id)
    if has_stocks:
        filtered_stocks = offers_repository.get_filtered_stocks(
            offer=offer,
            date=query.date,
            time=query.time,
            price_category_id=query.price_category_id,
            order_by=query.order_by,
            order_by_desc=query.order_by_desc,
            venue=offer.venue,
        )
        stocks_count = filtered_stocks.count()
        filtered_and_paginated_stocks = offers_repository.get_paginated_stocks(
            stocks_query=filtered_stocks,
            page=query.page,
            stocks_limit_per_page=query.stocks_limit_per_page,
        )
        stocks = [
            offers_serialize.GetOfferStockResponseModel.from_orm(stock) for stock in filtered_and_paginated_stocks.all()
        ]
    else:
        stocks = []
        stocks_count = 0
    return offers_serialize.GetStocksResponseModel(stocks=stocks, stock_count=stocks_count, has_stocks=has_stocks)


@private_api.route("/offers/<int:offer_id>/event_opening_hours", methods=["POST"])
@login_required
@spectree_serialize(
    on_success_status=201,
    response_model=offers_serialize.GetEventOpeningHoursResponseModel,
    api=blueprint.pro_private_schema,
)
@atomic()
def post_event_opening_hours(
    offer_id: int,
    body: offers_schemas.CreateEventOpeningHoursModel,
) -> offers_serialize.GetEventOpeningHoursResponseModel:
    try:
        offer = offers_repository.get_offer_by_id(offer_id)
    except exceptions.OfferNotFound:
        raise api_errors.ResourceNotFoundError(
            errors={
                "global": ["Aucun objet ne correspond à cet identifiant dans notre base de données"],
            }
        )

    rest.check_user_has_access_to_offerer(current_user, offer.venue.managingOffererId)
    try:
        event_opening_hours = offers_api.create_event_opening_hours(body=body, offer=offer)
    except exceptions.OfferException as error:
        raise api_errors.ApiErrors(errors=error.errors)

    return offers_serialize.GetEventOpeningHoursResponseModel.from_orm(event_opening_hours)


@private_api.route("/offers/<int:offer_id>/stocks/delete", methods=["POST"])
@login_required
@spectree_serialize(
    on_success_status=204,
    api=blueprint.pro_private_schema,
)
@atomic()
def delete_stocks(offer_id: int, body: offers_serialize.DeleteStockListBody) -> None:
    try:
        offer = offers_repository.get_offer_by_id(offer_id)
    except exceptions.OfferNotFound:
        raise api_errors.ApiErrors(
            errors={
                "global": ["Aucun objet ne correspond à cet identifiant dans notre base de données"],
            },
            status_code=404,
        )

    rest.check_user_has_access_to_offerer(current_user, offer.venue.managingOffererId)
    stocks_to_delete = [stock for stock in offer.stocks if stock.id in body.ids_to_delete]
    offers_api.batch_delete_stocks(stocks_to_delete, current_user.real_user.id, current_user.is_impersonated)


@private_api.route("/offers/<int:offer_id>/stocks/all-delete", methods=["POST"])
@login_required
@spectree_serialize(
    on_success_status=204,
    api=blueprint.pro_private_schema,
)
@atomic()
def delete_all_filtered_stocks(offer_id: int, body: offers_serialize.DeleteFilteredStockListBody) -> None:
    try:
        offer = offers_repository.get_offer_by_id(offer_id, load_options=["offerer_address"])
    except exceptions.OfferNotFound:
        raise api_errors.ApiErrors(
            errors={
                "global": ["Aucun objet ne correspond à cet identifiant dans notre base de données"],
            },
            status_code=404,
        )

    rest.check_user_has_access_to_offerer(current_user, offer.venue.managingOffererId)
    offers_repository.hard_delete_filtered_stocks(
        offer=offer,
        venue=offer.venue,
        date=body.date,
        time=body.time,
        price_category_id=body.price_category_id,
    )


@private_api.route("/offers/<int:offer_id>/stocks-stats", methods=["GET"])
@login_required
@spectree_serialize(
    response_model=offers_serialize.StockStatsResponseModel,
    api=blueprint.pro_private_schema,
)
@atomic()
def get_stocks_stats(offer_id: int) -> offers_serialize.StockStatsResponseModel:
    try:
        offer = offers_repository.get_offer_by_id(offer_id)
    except exceptions.OfferNotFound:
        raise api_errors.ApiErrors(
            errors={
                "global": ["Aucun objet ne correspond à cet identifiant dans notre base de données"],
            },
            status_code=404,
        )
    rest.check_user_has_access_to_offerer(current_user, offer.venue.managingOffererId)
    stocks_stats = offers_api.get_stocks_stats(offer_id=offer_id)
    return offers_serialize.StockStatsResponseModel(
        oldest_stock=stocks_stats.oldest_stock,
        newest_stock=stocks_stats.newest_stock,
        stock_count=stocks_stats.stock_count,
        remaining_quantity=stocks_stats.remaining_quantity,
    )


@private_api.route("/offers/delete-draft", methods=["POST"])
@login_required
@spectree_serialize(
    on_success_status=204,
    api=blueprint.pro_private_schema,
)
@atomic()
def delete_draft_offers(body: offers_serialize.DeleteOfferRequestBody) -> None:
    if not body.ids:
        raise api_errors.ApiErrors(
            errors={
                "global": ["Aucun objet ne correspond à cet identifiant dans notre base de données"],
            },
            status_code=404,
        )
    query = offers_repository.get_offers_by_ids(current_user, body.ids)  # type: ignore[arg-type]
    offers_api.batch_delete_draft_offers(query)


@private_api.route("/offers/draft", methods=["POST"])
@login_required
@spectree_serialize(
    response_model=offers_serialize.GetIndividualOfferResponseModel,
    on_success_status=201,
    api=blueprint.pro_private_schema,
)
@atomic()
def post_draft_offer(
    body: offers_schemas.PostDraftOfferBodyModel,
) -> offers_serialize.GetIndividualOfferResponseModel:
    venue: offerers_models.Venue = (
        db.session.query(offerers_models.Venue)
        .filter(offerers_models.Venue.id == body.venue_id)
        .options(sa_orm.joinedload(offerers_models.Venue.offererAddress))
        .first_or_404()
    )

    ean_code = body.extra_data.get("ean", None) if body.extra_data is not None else None
    product = (
        db.session.query(models.Product)
        .filter(models.Product.ean == ean_code)
        .filter(models.Product.id == body.product_id)
        .one_or_none()
    )

    rest.check_user_has_access_to_offerer(current_user, venue.managingOffererId)

    try:
        offer = offers_api.create_draft_offer(body, venue, product)
    except exceptions.OfferException as error:
        raise api_errors.ApiErrors(error.errors)
    return offers_serialize.GetIndividualOfferResponseModel.from_orm(offer)


@private_api.route("/offers/draft/<int:offer_id>", methods=["PATCH"])
@login_required
@spectree_serialize(
    response_model=offers_serialize.GetIndividualOfferResponseModel,
    api=blueprint.pro_private_schema,
)
@atomic()
def patch_draft_offer(
    offer_id: int, body: offers_schemas.PatchDraftOfferBodyModel
) -> offers_serialize.GetIndividualOfferResponseModel:
    offer = (
        db.session.query(models.Offer)
        .options(
            sa_orm.joinedload(models.Offer.stocks).joinedload(models.Stock.bookings),
            sa_orm.joinedload(models.Offer.venue).joinedload(offerers_models.Venue.managingOfferer),
            sa_orm.joinedload(models.Offer.product),
        )
        .get(offer_id)
    )
    if not offer:
        raise api_errors.ResourceNotFoundError

    rest.check_user_has_access_to_offerer(current_user, offer.venue.managingOffererId)
    try:
        if body_extra_data := offers_api.deserialize_extra_data(body.extra_data, offer.subcategoryId):
            body.extra_data = body_extra_data
        offer = offers_api.update_draft_offer(offer, body)
    except exceptions.OfferException as error:
        raise api_errors.ApiErrors(error.errors)

    return offers_serialize.GetIndividualOfferResponseModel.from_orm(offer)


@private_api.route("/offers", methods=["POST"])
@login_required
@spectree_serialize(
    response_model=offers_serialize.GetIndividualOfferResponseModel,
    on_success_status=201,
    api=blueprint.pro_private_schema,
)
@atomic()
def post_offer(body: offers_serialize.PostOfferBodyModel) -> offers_serialize.GetIndividualOfferResponseModel:
    venue: offerers_models.Venue = (
        db.session.query(offerers_models.Venue)
        .filter(offerers_models.Venue.id == body.venue_id)
        .options(sa_orm.joinedload(offerers_models.Venue.offererAddress))
        .first_or_404()
    )
    offerer_address: offerers_models.OffererAddress | None = None
    offerer_address = (
        offerers_api.get_offerer_address_from_address(venue.managingOffererId, body.address)
        if body.address
        else venue.offererAddress
    )
    rest.check_user_has_access_to_offerer(current_user, venue.managingOffererId)
    try:
        fields = body.dict(by_alias=True)
        fields.pop("venueId")
        fields.pop("address")
        fields["extraData"] = offers_api.deserialize_extra_data(fields["extraData"], fields["subcategoryId"])

        offer_body = offers_schemas.CreateOffer(**fields)
        offer = offers_api.create_offer(
            offer_body, venue=venue, offerer_address=offerer_address, is_from_private_api=True
        )
    except exceptions.OfferException as error:
        raise api_errors.ApiErrors(error.errors)

    return offers_serialize.GetIndividualOfferResponseModel.from_orm(offer)


@private_api.route("/offers/publish", methods=["PATCH"])
@login_required
@spectree_serialize(
    on_success_status=200,
    on_error_statuses=[404, 403],
    api=blueprint.pro_private_schema,
    response_model=offers_serialize.GetIndividualOfferResponseModel,
)
@atomic()
def patch_publish_offer(
    body: offers_serialize.PatchOfferPublishBodyModel,
) -> offers_serialize.GetIndividualOfferResponseModel:
    try:
        offerer = offerers_repository.get_by_offer_id(body.id)
    except offerers_exceptions.CannotFindOffererForOfferId:
        raise api_errors.ApiErrors({"offerer": ["Aucune structure trouvée à partir de cette offre"]}, status_code=404)

    rest.check_user_has_access_to_offerer(current_user, offerer.id)

    offer = offers_repository.get_offer_and_extradata(body.id)
    if offer is None:
        raise api_errors.ApiErrors({"offer": ["Cette offre n’existe pas"]}, status_code=404)
    if not offers_repository.offer_has_bookable_stocks(offer.id):
        raise api_errors.ApiErrors({"offer": "Cette offre n’a pas de stock réservable"}, 400)

    try:
        offers_api.update_offer_fraud_information(offer, user=current_user)
        offers_api.publish_offer(offer, publication_date=body.publicationDate)
    except exceptions.OfferException as exc:
        raise api_errors.ApiErrors(exc.errors)

    return offers_serialize.GetIndividualOfferResponseModel.from_orm(offer)


@private_api.route("/offers/active-status", methods=["PATCH"])
@login_required
@spectree_serialize(
    response_model=None,
    on_success_status=204,
    api=blueprint.pro_private_schema,
)
@atomic()
def patch_offers_active_status(body: offers_serialize.PatchOfferActiveStatusBodyModel) -> None:
    query = offers_repository.get_offers_by_ids(current_user, body.ids)

    publicationDatetime = None
    bookingAllowedDatetime = None

    if body.is_active:
        activation_datetime = datetime.datetime.now(datetime.timezone.utc)
        query = offers_repository.exclude_offers_from_inactive_venue_provider(query)
        offers_future_query = query.join(models.Offer.futureOffer)
        for offer in offers_future_query:
            reminders_notifications.notify_users_future_offer_activated(offer)
        publicationDatetime = activation_datetime
        bookingAllowedDatetime = activation_datetime

    offers_api.batch_update_offers(
        query,
        {
            "isActive": body.is_active,
            "bookingAllowedDatetime": bookingAllowedDatetime,
            "publicationDatetime": publicationDatetime,
        },
    )


@private_api.route("/offers/all-active-status", methods=["PATCH"])
@login_required
@spectree_serialize(
    response_model=None,
    on_success_status=202,
    api=blueprint.pro_private_schema,
)
@atomic()
def patch_all_offers_active_status(
    body: offers_serialize.PatchAllOffersActiveStatusBodyModel,
) -> offers_serialize.PatchAllOffersActiveStatusResponseModel:
    filters = {
        "user_id": current_user.id,
        "is_user_admin": current_user.has_admin_role,
        "offerer_id": body.offerer_id,
        "status": body.status,
        "venue_id": body.venue_id,
        "category_id": body.category_id,
        "name_or_ean": body.name_or_ean,
        "creation_mode": body.creation_mode,
        "period_beginning_date": body.period_beginning_date,
        "period_ending_date": body.period_ending_date,
        "offerer_address_id": body.offerer_address_id,
    }
    update_all_offers_active_status_job.delay(filters, body.is_active)
    return offers_serialize.PatchAllOffersActiveStatusResponseModel()


@private_api.route("/offers/<int:offer_id>", methods=["PATCH"])
@login_required
@spectree_serialize(
    response_model=offers_serialize.GetIndividualOfferResponseModel,
    api=blueprint.pro_private_schema,
)
@atomic()
def patch_offer(
    offer_id: int, body: offers_serialize.PatchOfferBodyModel
) -> offers_serialize.GetIndividualOfferResponseModel:
    try:
        offer = offers_repository.get_offer_by_id(
            offer_id,
            load_options=[
                "stock",
                "venue",
                "offerer_address",
                "product",
                "bookings_count",
                "is_non_free_offer",
                "event_opening_hours",
            ],
        )
    except exceptions.OfferNotFound:
        raise api_errors.ResourceNotFoundError()

    rest.check_user_has_access_to_offerer(current_user, offer.venue.managingOffererId)
    try:
        updates = body.dict(by_alias=True, exclude_unset=True)
        if body_extra_data := offers_api.deserialize_extra_data(body.extraData, offer.subcategoryId):
            if "ean" in body_extra_data:
                updates["ean"] = body_extra_data.pop("ean")
            updates["extraData"] = body_extra_data

        offer_body = offers_schemas.UpdateOffer(**updates)

        offer = offers_api.update_offer(offer, offer_body, is_from_private_api=True)
    except exceptions.OfferException as error:
        raise api_errors.ApiErrors(error.errors)

    return offers_serialize.GetIndividualOfferResponseModel.from_orm(offer)


@private_api.route("/offers/thumbnails/", methods=["POST"])
@login_required
@spectree_serialize(
    on_success_status=201,
    response_model=CreateThumbnailResponseModel,
    api=blueprint.pro_private_schema,
)
@atomic()
def create_thumbnail(form: CreateThumbnailBodyModel) -> CreateThumbnailResponseModel:
    try:
        offer = offers_repository.get_offer_by_id(form.offer_id)
    except exceptions.OfferNotFound:
        raise api_errors.ApiErrors(
            errors={
                "global": ["Aucun objet ne correspond à cet identifiant dans notre base de données"],
            },
            status_code=404,
        )
    rest.check_user_has_access_to_offerer(current_user, offer.venue.managingOffererId)

    image_as_bytes = form.get_image_as_bytes(request)

    thumbnail = offers_api.create_mediation(
        user=current_user,
        offer=offer,
        credit=form.credit,
        image_as_bytes=image_as_bytes,
        crop_params=form.crop_params,
        min_width=None,
        min_height=None,
    )

    return CreateThumbnailResponseModel(id=thumbnail.id, url=thumbnail.thumbUrl, credit=thumbnail.credit)  # type: ignore[arg-type]


@private_api.route("/offers/thumbnails/<int:offer_id>", methods=["DELETE"])
@login_required
@spectree_serialize(
    on_success_status=204,
    api=blueprint.pro_private_schema,
)
@atomic()
def delete_thumbnail(offer_id: int) -> None:
    offer = db.session.query(models.Offer).get_or_404(offer_id)

    rest.check_user_has_access_to_offerer(current_user, offer.venue.managingOffererId)

    offers_api.delete_mediations([offer_id])


@private_api.route("/offers/categories", methods=["GET"])
@login_required
@spectree_serialize(
    response_model=offers_serialize.CategoriesResponseModel,
    api=blueprint.pro_private_schema,
)
@atomic()
def get_categories() -> offers_serialize.CategoriesResponseModel:
    return offers_serialize.CategoriesResponseModel(
        categories=[
            offers_serialize.CategoryResponseModel.from_orm(category) for category in pro_categories.ALL_CATEGORIES
        ],
        subcategories=[
            offers_serialize.SubcategoryResponseModel.from_orm(subcategory)
            for subcategory in subcategories.ALL_SUBCATEGORIES
        ],
    )


def create_prompt(name: str, description: str | None) -> str:
    prompt = """`
Tu es un expert en classification d'offres. Tu es capable de deviner la catégorie et la sous-catégorie d'une offre en fonction de son titre et de sa description.

Voici les catégories et sous-catégories disponibles sous forme d'objet JSON :

categories = [
  { id: 'BEAUX_ARTS', proLabel: 'Beaux-arts' },
  { id: 'CARTE_JEUNES', proLabel: 'Carte jeunes' },
  { id: 'CINEMA', proLabel: 'Cinéma' },
  { id: 'CONFERENCE', proLabel: 'Conférences, rencontres' },
  { id: 'FILM', proLabel: 'Films, vidéos' },
  { id: 'INSTRUMENT', proLabel: 'Instrument de musique' },
  { id: 'JEU', proLabel: 'Jeux' },
  { id: 'LIVRE', proLabel: 'Livre' },
  { id: 'MEDIA', proLabel: 'Médias' },
  { id: 'MUSEE', proLabel: 'Musée, patrimoine, architecture, arts visuels' },
  { id: 'MUSIQUE_ENREGISTREE', proLabel: 'Musique enregistrée' },
  { id: 'MUSIQUE_LIVE', proLabel: 'Musique live' },
  { id: 'PRATIQUE_ART', proLabel: 'Pratique artistique' },
  { id: 'SPECTACLE', proLabel: 'Spectacle vivant' },
  { id: 'TECHNIQUE', proLabel: 'Catégorie technique' }
]

subcategories = [
  {
    id: 'ABO_BIBLIOTHEQUE',
    categoryId: 'LIVRE',
    proLabel: 'Abonnement (bibliothèques, médiathèques...)'
  },
  {
    id: 'ABO_CONCERT',
    categoryId: 'MUSIQUE_LIVE',
    proLabel: 'Abonnement concert'
  },
  {
    id: 'ABO_JEU_VIDEO',
    categoryId: 'JEU',
    proLabel: 'Abonnement jeux vidéos'
  },
  {
    id: 'ABO_LIVRE_NUMERIQUE',
    categoryId: 'LIVRE',
    proLabel: 'Abonnement livres numériques'
  },
  {
    id: 'ABO_LUDOTHEQUE',
    categoryId: 'JEU',
    proLabel: 'Abonnement ludothèque'
  },
  {
    id: 'ABO_MEDIATHEQUE',
    categoryId: 'FILM',
    proLabel: 'Abonnement médiathèque'
  },
  {
    id: 'ABO_PLATEFORME_MUSIQUE',
    categoryId: 'MUSIQUE_ENREGISTREE',
    proLabel: 'Abonnement plateforme musicale'
  },
  {
    id: 'ABO_PLATEFORME_VIDEO',
    categoryId: 'FILM',
    proLabel: 'Abonnement plateforme streaming'
  },
  {
    id: 'ABO_PRATIQUE_ART',
    categoryId: 'PRATIQUE_ART',
    proLabel: 'Abonnement pratique artistique'
  },
  {
    id: 'ABO_PRESSE_EN_LIGNE',
    categoryId: 'MEDIA',
    proLabel: 'Abonnement presse en ligne'
  },
  {
    id: 'ABO_SPECTACLE',
    categoryId: 'SPECTACLE',
    proLabel: 'Abonnement spectacle'
  },
  {
    id: 'ACHAT_INSTRUMENT',
    categoryId: 'INSTRUMENT',
    proLabel: 'Achat instrument'
  },
  {
    id: 'ACTIVATION_EVENT',
    categoryId: 'TECHNIQUE',
    proLabel: "Catégorie technique d'évènement d'activation "
  },
  {
    id: 'ACTIVATION_THING',
    categoryId: 'TECHNIQUE',
    proLabel: "Catégorie technique de thing d'activation"
  },
  {
    id: 'APP_CULTURELLE',
    categoryId: 'MEDIA',
    proLabel: 'Application culturelle'
  },
  {
    id: 'ATELIER_PRATIQUE_ART',
    categoryId: 'PRATIQUE_ART',
    proLabel: 'Atelier, stage de pratique artistique'
  },
  {
    id: 'AUTRE_SUPPORT_NUMERIQUE',
    categoryId: 'FILM',
    proLabel: 'Autre support numérique'
  },
  {
    id: 'BON_ACHAT_INSTRUMENT',
    categoryId: 'INSTRUMENT',
    proLabel: "Bon d'achat instrument"
  },
  {
    id: 'CAPTATION_MUSIQUE',
    categoryId: 'MUSIQUE_ENREGISTREE',
    proLabel: 'Captation musicale'
  },
  {
    id: 'CARTE_CINE_ILLIMITE',
    categoryId: 'CINEMA',
    proLabel: 'Carte cinéma illimité'
  },
  {
    id: 'CARTE_CINE_MULTISEANCES',
    categoryId: 'CINEMA',
    proLabel: 'Carte cinéma multi-séances'
  },
  {
    id: 'CARTE_JEUNES',
    categoryId: 'CARTE_JEUNES',
    proLabel: 'Carte jeunes'
  },
  {
    id: 'CARTE_MUSEE',
    categoryId: 'MUSEE',
    proLabel: 'Abonnement musée, carte ou pass'
  },
  {
    id: 'CINE_PLEIN_AIR',
    categoryId: 'CINEMA',
    proLabel: 'Cinéma plein air'
  },
  {
    id: 'CINE_VENTE_DISTANCE',
    categoryId: 'CINEMA',
    proLabel: 'Cinéma vente à distance'
  },
  { id: 'CONCERT', categoryId: 'MUSIQUE_LIVE', proLabel: 'Concert' },
  { id: 'CONCOURS', categoryId: 'JEU', proLabel: 'Concours - jeux' },
  {
    id: 'CONFERENCE',
    categoryId: 'CONFERENCE',
    proLabel: 'Conférence'
  },
  {
    id: 'DECOUVERTE_METIERS',
    categoryId: 'CONFERENCE',
    proLabel: 'Découverte des métiers'
  },
  { id: 'ESCAPE_GAME', categoryId: 'JEU', proLabel: 'Escape game' },
  {
    id: 'EVENEMENT_CINE',
    categoryId: 'CINEMA',
    proLabel: 'Évènement cinématographique'
  },
  {
    id: 'EVENEMENT_JEU',
    categoryId: 'JEU',
    proLabel: 'Évènements - jeux'
  },
  {
    id: 'EVENEMENT_MUSIQUE',
    categoryId: 'MUSIQUE_LIVE',
    proLabel: "Autre type d'évènement musical"
  },
  {
    id: 'EVENEMENT_PATRIMOINE',
    categoryId: 'MUSEE',
    proLabel: 'Évènement et atelier patrimoine'
  },
  {
    id: 'FESTIVAL_ART_VISUEL',
    categoryId: 'MUSEE',
    proLabel: "Festival d'arts visuels / arts numériques"
  },
  {
    id: 'FESTIVAL_CINE',
    categoryId: 'CINEMA',
    proLabel: 'Festival de cinéma'
  },
  {
    id: 'FESTIVAL_LIVRE',
    categoryId: 'LIVRE',
    proLabel: 'Festival et salon du livre'
  },
  {
    id: 'FESTIVAL_MUSIQUE',
    categoryId: 'MUSIQUE_LIVE',
    proLabel: 'Festival de musique'
  },
  {
    id: 'FESTIVAL_SPECTACLE',
    categoryId: 'SPECTACLE',
    proLabel: 'Festival de spectacle vivant'
  },
  { id: 'JEU_EN_LIGNE', categoryId: 'JEU', proLabel: 'Jeux en ligne' },
  {
    id: 'JEU_SUPPORT_PHYSIQUE',
    categoryId: 'TECHNIQUE',
    proLabel: 'Catégorie technique Jeu support physique'
  },
  {
    id: 'LIVESTREAM_EVENEMENT',
    categoryId: 'SPECTACLE',
    proLabel: "Livestream d'évènement"
  },
  {
    id: 'LIVESTREAM_MUSIQUE',
    categoryId: 'MUSIQUE_LIVE',
    proLabel: 'Livestream musical'
  },
  {
    id: 'LIVESTREAM_PRATIQUE_ARTISTIQUE',
    categoryId: 'PRATIQUE_ART',
    proLabel: 'Pratique artistique - livestream'
  },
  {
    id: 'LIVRE_AUDIO_PHYSIQUE',
    categoryId: 'LIVRE',
    proLabel: 'Livre audio sur support physique'
  },
  {
    id: 'LIVRE_NUMERIQUE',
    categoryId: 'LIVRE',
    proLabel: 'Livre numérique, e-book'
  },
  { id: 'LIVRE_PAPIER', categoryId: 'LIVRE', proLabel: 'Livre papier' },
  {
    id: 'LOCATION_INSTRUMENT',
    categoryId: 'INSTRUMENT',
    proLabel: 'Location instrument'
  },
  {
    id: 'MATERIEL_ART_CREATIF',
    categoryId: 'BEAUX_ARTS',
    proLabel: 'Matériel arts créatifs'
  },
  {
    id: 'MUSEE_VENTE_DISTANCE',
    categoryId: 'MUSEE',
    proLabel: 'Musée vente à distance'
  },
  {
    id: 'OEUVRE_ART',
    categoryId: 'TECHNIQUE',
    proLabel: "Catégorie technique d'oeuvre d'art"
  },
  { id: 'PARTITION', categoryId: 'INSTRUMENT', proLabel: 'Partition' },
  {
    id: 'PLATEFORME_PRATIQUE_ARTISTIQUE',
    categoryId: 'PRATIQUE_ART',
    proLabel: 'Pratique artistique - plateforme en ligne'
  },
  {
    id: 'PRATIQUE_ART_VENTE_DISTANCE',
    categoryId: 'PRATIQUE_ART',
    proLabel: 'Pratique artistique - vente à distance'
  },
  { id: 'PODCAST', categoryId: 'MEDIA', proLabel: 'Podcast' },
  {
    id: 'RENCONTRE_EN_LIGNE',
    categoryId: 'CONFERENCE',
    proLabel: 'Rencontre en ligne'
  },
  {
    id: 'RENCONTRE_JEU',
    categoryId: 'JEU',
    proLabel: 'Rencontres - jeux'
  },
  { id: 'RENCONTRE', categoryId: 'CONFERENCE', proLabel: 'Rencontre' },
  {
    id: 'SALON',
    categoryId: 'CONFERENCE',
    proLabel: 'Salon, Convention'
  },
  {
    id: 'SEANCE_CINE',
    categoryId: 'CINEMA',
    proLabel: 'Séance de cinéma'
  },
  {
    id: 'SEANCE_ESSAI_PRATIQUE_ART',
    categoryId: 'PRATIQUE_ART',
    proLabel: "Séance d'essai"
  },
  {
    id: 'SPECTACLE_ENREGISTRE',
    categoryId: 'SPECTACLE',
    proLabel: 'Spectacle enregistré'
  },
  {
    id: 'SPECTACLE_REPRESENTATION',
    categoryId: 'SPECTACLE',
    proLabel: 'Spectacle, représentation'
  },
  {
    id: 'SPECTACLE_VENTE_DISTANCE',
    categoryId: 'SPECTACLE',
    proLabel: 'Spectacle vivant - vente à distance'
  },
  {
    id: 'SUPPORT_PHYSIQUE_FILM',
    categoryId: 'FILM',
    proLabel: 'Support physique (DVD, Blu-ray...)'
  },
  {
    id: 'SUPPORT_PHYSIQUE_MUSIQUE_CD',
    categoryId: 'MUSIQUE_ENREGISTREE',
    proLabel: 'CD'
  },
  {
    id: 'SUPPORT_PHYSIQUE_MUSIQUE_VINYLE',
    categoryId: 'MUSIQUE_ENREGISTREE',
    proLabel: 'Vinyles et autres supports'
  },
  {
    id: 'TELECHARGEMENT_LIVRE_AUDIO',
    categoryId: 'LIVRE',
    proLabel: 'Livre audio à télécharger'
  },
  {
    id: 'TELECHARGEMENT_MUSIQUE',
    categoryId: 'MUSIQUE_ENREGISTREE',
    proLabel: 'Téléchargement de musique'
  },
  {
    id: 'VISITE_GUIDEE',
    categoryId: 'MUSEE',
    proLabel: 'Visite guidée'
  },
  {
    id: 'VISITE_VIRTUELLE',
    categoryId: 'MUSEE',
    proLabel: 'Visite virtuelle'
  },
  { id: 'VISITE', categoryId: 'MUSEE', proLabel: 'Visite' },
  { id: 'VOD', categoryId: 'FILM', proLabel: 'Vidéo à la demande' }
]

La relation entre les catégories et les sous-catégories se fait par l'ID de la catégorie dans chaque objet de sous-catégories.

Tu dois retourner un objet JSON avec les clés "category" et "subcategory" qui sont les ID des catégories et sous-catégories correspondantes.

Voici un exemple de ce que tu dois faire systématiquement :

Pour le texte entrant suivant "Guitare acoustique excellent état" tu dois retourner :

{
  "category": "INSTRUMENT",
  "subcategory": "ACHAT_INSTRUMENT"
}

Pour le texte entrant suivant "Abonnement à la presse en ligne" tu dois retourner :

{
  "category": "MEDIA",
  "subcategory": "ABO_PRESSE_EN_LIGNE"
}

Tu devras TOUJOURS retourner un objet JSON avec les clés "category" et "subcategory". Si tu ne trouves pas la catégorie, tu dois retourner "category": "TECHNIQUE".
Et si tu ne trouves pas la sous-catégorie, tu dois retourner "subcategory": "AUTRE".

À noter que le domaine d'activité est le domaine de la culture et des offres culturelles au sens large. Tu utilisera donc tes connaissances dans les offres culturelles pour trouver la catégorie et la sous-catégorie.

Voici le texte entrant : """
    if description:
        return prompt + name + " " + description
    return prompt + name


# HACKATON bdalbianco
@private_api.route("/offers/categories_automatic", methods=["POST"])
# @login_required
# @spectree_serialize(
#     # response_model=offers_serialize.CategoriesResponseModel,
#     response_model=dict(),
#     api=blueprint.pro_private_schema,
# )
# @atomic()
def fetch_categories_auto() -> dict:
    # if FeatureToggle.WIP_HACKATON_AUTOMATICALLY_ASSIGN_OFFER_CATEGORY:
    data = request.get_json()
    name = data.get("name")
    description = data.get("description")
    prompt = create_prompt(name, description)

    api_key = os.environ.get("OPENAPI_KEY")
    client = OpenAI(api_key=api_key)
    completion = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}])
    import json

    print(completion)
    print(json.loads(completion.choices[0].message.content))
    res = json.loads(completion.choices[0].message.content)
    print(res["category"], res["subcategory"])
    return res


@private_api.route("/offers/music-types", methods=["GET"])
@login_required
@spectree_serialize(
    response_model=offers_serialize.GetMusicTypesResponse,
    api=blueprint.pro_private_schema,
)
@atomic()
def get_music_types() -> offers_serialize.GetMusicTypesResponse:
    return offers_serialize.GetMusicTypesResponse(
        __root__=[
            offers_serialize.MusicTypeResponse(
                gtl_id=music_type.gtl_id, label=music_type.label, canBeEvent=music_type.can_be_event
            )
            for music_type in TITELIVE_MUSIC_TYPES
        ]
    )


def _get_offer_for_price_categories_upsert(
    offer_id: int, price_category_edition_payload: list[offers_serialize.EditPriceCategoryModel]
) -> models.Offer | None:
    return (
        db.session.query(models.Offer)
        .outerjoin(models.Offer.stocks.and_(sqla.not_(models.Stock.isEventExpired)))
        .outerjoin(
            models.Offer.priceCategories.and_(
                models.PriceCategory.id.in_([price_category.id for price_category in price_category_edition_payload])
            )
        )
        .outerjoin(models.PriceCategoryLabel, models.PriceCategory.priceCategoryLabel)
        .options(sa_orm.contains_eager(models.Offer.stocks))
        .options(
            sa_orm.contains_eager(models.Offer.priceCategories).contains_eager(models.PriceCategory.priceCategoryLabel)
        )
        .filter(models.Offer.id == offer_id)
        .one_or_none()
    )


@private_api.route("/offers/<int:offer_id>/price_categories", methods=["POST"])
@login_required
@spectree_serialize(
    response_model=offers_serialize.GetIndividualOfferResponseModel,
    api=blueprint.pro_private_schema,
)
@atomic()
def post_price_categories(
    offer_id: int, body: offers_serialize.PriceCategoryBody
) -> offers_serialize.GetIndividualOfferResponseModel:
    price_categories_to_create = [
        price_category
        for price_category in body.price_categories
        if isinstance(price_category, offers_serialize.CreatePriceCategoryModel)
    ]
    price_categories_to_edit = [
        price_category
        for price_category in body.price_categories
        if isinstance(price_category, offers_serialize.EditPriceCategoryModel)
    ]

    new_labels_and_prices = {(p.label, p.price) for p in price_categories_to_create}
    validation.check_for_duplicated_price_categories(new_labels_and_prices, offer_id)

    offer = _get_offer_for_price_categories_upsert(offer_id, price_categories_to_edit)
    if not offer:
        raise api_errors.ApiErrors({"offer_id": ["L'offre avec l'id %s n'existe pas" % offer_id]}, status_code=400)
    rest.check_user_has_access_to_offerer(current_user, offer.venue.managingOffererId)

    existing_price_categories_by_id = {category.id: category for category in offer.priceCategories}

    for price_category_to_create in price_categories_to_create:
        offers_api.create_price_category(offer, price_category_to_create.label, price_category_to_create.price)

    for price_category_to_edit in price_categories_to_edit:
        if price_category_to_edit.id not in existing_price_categories_by_id:
            raise api_errors.ApiErrors(
                {"price_category_id": ["Le tarif avec l'id %s n'existe pas" % price_category_to_edit.id]},
                status_code=400,
            )
        data = price_category_to_edit.dict(exclude_unset=True)
        try:
            offers_api.edit_price_category(
                offer,
                price_category=existing_price_categories_by_id[data["id"]],
                label=data.get("label", offers_api.UNCHANGED),
                price=data.get("price", offers_api.UNCHANGED),
            )
        except exceptions.OfferException as exc:
            raise api_errors.ApiErrors(exc.errors)

    # Since we modified the price categories, we need to push the changes to the database
    # so that the response does include them
    db.session.flush()

    return offers_serialize.GetIndividualOfferResponseModel.from_orm(offer)


@private_api.route("/offers/<int:offer_id>/price_categories/<int:price_category_id>", methods=["DELETE"])
@login_required
@spectree_serialize(api=blueprint.pro_private_schema, on_success_status=204)
@atomic()
def delete_price_category(offer_id: int, price_category_id: int) -> None:
    offer = db.session.query(models.Offer).get_or_404(offer_id)
    rest.check_user_has_access_to_offerer(current_user, offer.venue.managingOffererId)

    price_category = db.session.query(models.PriceCategory).get_or_404(price_category_id)
    offers_api.delete_price_category(offer, price_category)


@private_api.route("/offers/<int:venue_id>/ean/<string:ean>", methods=["GET"])
@login_required
@spectree_serialize(
    response_model=offers_serialize.GetActiveEANOfferResponseModel,
    api=blueprint.pro_private_schema,
)
@atomic()
def get_active_venue_offer_by_ean(venue_id: int, ean: str) -> offers_serialize.GetActiveEANOfferResponseModel:
    try:
        venue = offerers_repository.get_venue_by_id(venue_id)
        rest.check_user_has_access_to_offerer(current_user, venue.managingOffererId)
        offer = offers_repository.get_active_offer_by_venue_id_and_ean(venue_id, ean)
    except exceptions.OfferNotFound:
        raise api_errors.ApiErrors(
            errors={
                "global": ["Aucun objet ne correspond à cet identifiant dans notre base de données"],
            },
            status_code=404,
        )

    return offers_serialize.GetActiveEANOfferResponseModel.from_orm(offer)


@private_api.route("/get_product_by_ean/<string:ean>/<int:offerer_id>", methods=["GET"])
@login_required
@spectree_serialize(
    response_model=offers_serialize.GetProductInformations,
    api=blueprint.pro_private_schema,
)
@atomic()
def get_product_by_ean(ean: str, offerer_id: int) -> offers_serialize.GetProductInformations:
    product = (
        db.session.query(models.Product)
        .filter(models.Product.ean == ean)
        .options(
            sa_orm.load_only(
                models.Product.id,
                models.Product.extraData,
                models.Product.gcuCompatibilityType,
                models.Product.name,
                models.Product.description,
                models.Product.subcategoryId,
                models.Product.thumbCount,
            )
        )
        .options(sa_orm.joinedload(models.Product.productMediations))
        .one_or_none()
    )
    offerer = (
        db.session.query(offerers_models.Offerer)
        .filter_by(id=offerer_id)
        .options(sa_orm.load_only(offerers_models.Offerer.id))
        .options(
            sa_orm.joinedload(offerers_models.Offerer.managedVenues).load_only(
                offerers_models.Venue.id, offerers_models.Venue.isVirtual
            )
        )
        .one_or_none()
    )
    validation.check_product_cgu_and_offerer(product, ean, offerer)
    return offers_serialize.GetProductInformations.from_orm(product=product)


@private_api.route("/offers/<int:offer_id>/event_opening_hours/<int:event_opening_hours_id>", methods=["PATCH"])
@login_required
@spectree_serialize(api=blueprint.pro_private_schema, on_success_status=204)
@atomic()
def update_event_opening_hours(
    offer_id: int, event_opening_hours_id: int, body: offers_schemas.UpdateEventOpeningHoursModel
) -> None:
    offer = db.session.query(models.Offer).get_or_404(offer_id)
    rest.check_user_has_access_to_offerer(current_user, offer.venue.managingOffererId)

    opening_hours = (
        db.session.query(models.EventOpeningHours)
        .filter(models.EventOpeningHours.id == event_opening_hours_id, models.EventOpeningHours.offerId == offer_id)
        .options(sa_orm.selectinload(models.EventOpeningHours.weekDayOpeningHours))
        .first()
    )
    if not opening_hours:
        raise NotFound()

    try:
        offers_api.update_event_opening_hours(opening_hours, body)
    except exceptions.EventOpeningHoursException as error:
        raise api_errors.ApiErrors(errors={error.field: [error.msg]})
    except exceptions.OfferException as error:
        raise api_errors.ApiErrors(errors=error.errors)


@private_api.route("/offers/<int:offer_id>/event_opening_hours/<int:event_opening_hours_id>", methods=["DELETE"])
@login_required
@spectree_serialize(api=blueprint.pro_private_schema, on_success_status=204)
@atomic()
def delete_event_opening_hours(offer_id: int, event_opening_hours_id: int) -> None:
    offer = (
        db.session.query(models.Offer)
        .filter(models.Offer.id == offer_id)
        .options(
            sa_orm.joinedload(models.Offer.venue).load_only(offerers_models.Venue.managingOffererId),
            sa_orm.selectinload(models.Offer.stocks).selectinload(models.Stock.bookings),
        )
        .one_or_none()
    )

    if not offer:
        raise NotFound()

    rest.check_user_has_access_to_offerer(current_user, offer.venue.managingOffererId)

    opening_hours = (
        db.session.query(models.EventOpeningHours)
        .filter(models.EventOpeningHours.offerId == offer_id, models.EventOpeningHours.id == event_opening_hours_id)
        .options(sa_orm.joinedload(models.EventOpeningHours.weekDayOpeningHours))
        .one_or_none()
    )

    if not opening_hours:
        raise NotFound()

    try:
        offers_api.delete_event_opening_hours(opening_hours)
    except exceptions.EventOpeningHoursException as error:
        raise api_errors.ApiErrors(errors={error.field: [error.msg]}, status_code=400)
