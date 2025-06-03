import datetime
import json
import logging
import os

import sqlalchemy as sqla
import sqlalchemy.orm as sa_orm
from flask import request
from flask_login import current_user
from flask_login import login_required
from google import genai
from openai import OpenAI
from werkzeug.exceptions import NotFound
from pcapi.repository import repository
import pcapi.core.offers.models as offers_models

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
    descr = '" DESCRIPTION = "'
    prompt = """
Tu es un expert en classification d'offres. Tu es capable de deviner la catégorie et la sous-catégorie d'une offre en fonction de son titre et de sa description.

Voici les catégories et sous-catégories disponibles :
(Catégorie ; category_ID ; Sous-catégorie ; subcategory_ID ; Définition) ; (Beaux-arts ; BEAUX_ARTS ; Matériel arts créatifs ; MATERIEL_ART_CREATIF ; Fournitures utilisées pour les activités de création artistique (peinture, dessin, sculpture, etc.).) ; (Carte jeunes ; CARTE_JEUNES ; Carte jeunes ; CARTE_JEUNES ; Carte offrant des réductions ou avantages culturels aux jeunes (cinéma, concerts, musées, etc.).) ; (Cinéma ; CINEMA ; Carte cinéma illimité ; CARTE_CINE_ILLIMITE ; Abonnement permettant un accès illimité aux séances de cinéma dans un réseau spécifique.) ; (Cinéma ; CINEMA ; Carte cinéma multi-séances ; CARTE_CINE_MULTISEANCES ; Carte prépayée pour un nombre déterminé de séances, avec un retrait physique au guichet du cinéma) ; (Cinéma ; CINEMA ; Cinéma plein air ; CINE_PLEIN_AIR ; Projection de films organisée en extérieur, généralement en été.) ; (Cinéma ; CINEMA ; Séance de cinéma ; SEANCE_CINE ; Billet pour assister à une projection dans une salle de cinéma.) ; (Cinéma ; CINEMA ; Évènement cinématographique ; EVENEMENT_CINE ; Manifestation spéciale autour du cinéma (avant-première, rétrospective, rencontre…)) ; (Cinéma ; CINEMA ; Festival de cinéma ; FESTIVAL_CINE ; Manifestation regroupant la projection de films selon une thématique ou une compétition.) ; (Cinéma ; CINEMA ; Cinéma vente à distance ; CINE_VENTE_DISTANCE ; Achat en ligne de cartes de cinéma avec envoi de la carte par mail au jeune) ; (Conférences, rencontres ; CONFERENCE ; Conférence ; CONFERENCE ; Exposé oral sur un sujet spécifique, souvent avec questions/réponses) ; (Conférences, rencontres ; CONFERENCE ; Rencontre ; RENCONTRE ; Échange direct avec une personnalité ou un expert (auteur, artiste, etc.)) ; (Conférences, rencontres ; CONFERENCE ; Salon, Convention ; SALON ; Évènement rassemblant exposants et visiteurs autour d'un thème (livre, jeu, science…)) ; (Conférences, rencontres ; CONFERENCE ; Rencontre en ligne ; RENCONTRE_EN_LIGNE ; Évènement interactif à distance, souvent via visioconférence.) ; (Films, vidéos ; FILM ; Abonnement médiathèque ; ABO_MEDIATHEQUE ; Accès régulier à une médiathèque incluant films, vidéos, supports culturels.) ; (Films, vidéos ; FILM ; Support physique (DVD, Blu-ray...) ; SUPPORT_PHYSIQUE_FILM ; Achat de films ou vidéos sur support matériel.) ; (Films, vidéos ; FILM ; Abonnement plateforme streaming ; ABO_PLATEFORME_VIDEO ; Abonnement à un service de diffusion de films/séries en ligne.) ; (Films, vidéos ; FILM ; Autre support numérique ; AUTRE_SUPPORT_NUMERIQUE ; Films ou vidéos accessibles en téléchargement ou clé USB, hors plateformes traditionnelles.) ; (Films, vidéos ; FILM ; Vidéo à la demande ; VOD ; Location ou achat ponctuel de films en ligne (à l'unité).) ; (Instrument de musique ; INSTRUMENT ; Achat instrument ; ACHAT_INSTRUMENT ; Acquisition d'un instrument de musique (neuf ou occasion).) ; (Instrument de musique ; INSTRUMENT ; Location instrument ; LOCATION_INSTRUMENT ; Mise à disposition temporaire d'un instrument moyennant un loyer.) ; (Instrument de musique ; INSTRUMENT ; Partition ; PARTITION ; Achat de partitions papier ou numériques pour jouer de la musique.) ; (Instrument de musique ; INSTRUMENT ; Bon d'achat instrument ; BON_ACHAT_INSTRUMENT ; Carte ou crédit valable pour acheter un instrument.) ; (Jeux ; JEU ; Escape game ; ESCAPE_GAME ; Jeu d'évasion grandeur nature basé sur la résolution d'énigmes.) ; (Jeux ; JEU ; Concours - jeux ; CONCOURS ; Participation à un concours ou jeu à visée ludique ou compétitive.) ; (Jeux ; JEU ; Évènements - jeux ; EVENEMENT_JEU ; Manifestation rassemblant joueurs autour d'un jeu ou d'un univers ludique.) ; (Jeux ; JEU ; Rencontres - jeux ; RENCONTRE_JEU ; Session organisée de jeu collectif (soirée jeux de société, tournoi, etc.).) ; (Jeux ; JEU ; Abonnement jeux vidéos ; ABO_JEU_VIDEO ; Accès illimité à une sélection de jeux vidéo via abonnement.) ; (Jeux ; JEU ; Jeux en ligne ; JEU_EN_LIGNE ; Jeux accessibles via internet (MMORPG, plateformes de jeux, etc.).) ; (Livre ; LIVRE ; Abonnement (bibliothèques, médiathèques...) ; ABO_BIBLIOTHEQUE ; Accès régulier à des livres via une structure culturelle.) ; (Livre ; LIVRE ; Livre papier ; LIVRE_PAPIER ; Livre imprimé traditionnel.) ; (Livre ; LIVRE ; Livre audio sur support physique ; LIVRE_AUDIO_PHYSIQUE ; Livre lu enregistré sur CD ou autre support tangible.) ; (Livre ; LIVRE ; Festival et salon du livre ; FESTIVAL_LIVRE ; Évènement dédié à la littérature, auteurs, éditeurs et lecteurs.) ; (Livre ; LIVRE ; Abonnement livres numériques ; ABO_LIVRE_NUMERIQUE ; Accès illimité ou régulier à des e-books via abonnement.) ; (Livre ; LIVRE ; Livre numérique, e-book ; LIVRE_NUMERIQUE ; Fichier téléchargeable lisible sur liseuse, tablette ou ordinateur.) ; (Livre ; LIVRE ; Livre audio à télécharger ; TELECHARGEMENT_LIVRE_AUDIO ; Livre lu disponible en téléchargement, sans support physique.) ; (Musée, patrimoine, architecture, arts visuels ; MUSEE ; Abonnement musée, carte ou pass ; CARTE_MUSEE ; Entrée libre ou réduite à des musées via une carte annuelle.) ; (Musée, patrimoine, architecture, arts visuels ; MUSEE ; Évènement et atelier patrimoine ; EVENEMENT_PATRIMOINE ; Activités pédagogiques ou festives liées au patrimoine historique ou artistique.) ; (Musée, patrimoine, architecture, arts visuels ; MUSEE ; Festival d'arts visuels / arts numériques ; FESTIVAL_ART_VISUEL ; Manifestation autour de la création visuelle contemporaine (installations, projections, VR...).) ; (Musée, patrimoine, architecture, arts visuels ; MUSEE ; Visite guidée ; VISITE_GUIDEE ; Parcours accompagné d'un guide professionnel.) ; (Musée, patrimoine, architecture, arts visuels ; MUSEE ; Visite ; VISITE ; Accès libre à un lieu culturel (musée, monument, expo...).) ; (Musée, patrimoine, architecture, arts visuels ; MUSEE ; Musée vente à distance ; MUSEE_VENTE_DISTANCE ; Billets ou produits liés au musée achetés en ligne) ; (Musée, patrimoine, architecture, arts visuels ; MUSEE ; Visite virtuelle ; VISITE_VIRTUELLE ; Exploration numérique d'un lieu culturel.) ; (Médias ; MEDIA ; Abonnement presse en ligne ; ABO_PRESSE_EN_LIGNE ; Accès payant à des journaux ou magazines numériques.) ; (Médias ; MEDIA ; Application culturelle ; APP_CULTURELLE ; Appli mobile dédiée à la découverte ou l'usage de contenus culturels.) ; (Médias ; MEDIA ; Podcast ; PODCAST ; Émission audio à la demande sur un sujet culturel ou artistique.) ; (Musique enregistrée ; MUSIQUE_ENREGISTREE ; CD ; SUPPORT_PHYSIQUE_MUSIQUE_CD ; Support optique contenant de la musique.) ; (Musique enregistrée ; MUSIQUE_ENREGISTREE ; Vinyles et autres supports ; SUPPORT_PHYSIQUE_MUSIQUE_VINYLE ; Supports analogiques ou alternatifs au CD (vinyle, cassette…).) ; (Musique enregistrée ; MUSIQUE_ENREGISTREE ; Abonnement plateforme musicale ; ABO_PLATEFORME_MUSIQUE ; Accès illimité à un catalogue musical en ligne (Spotify, Deezer…).) ; (Musique enregistrée ; MUSIQUE_ENREGISTREE ; Téléchargement de musique ; TELECHARGEMENT_MUSIQUE ; Achat définitif de fichiers musicaux numériques.) ; (Musique live ; MUSIQUE_LIVE ; Abonnement concert ; ABO_CONCERT ; Pass ou abonnement pour assister à des concerts en illimité ou à tarif réduit.) ; (Musique live ; MUSIQUE_LIVE ; Autre type d'évènement musical ; EVENEMENT_MUSIQUE ; Soirée DJ, jam session, performance musicale hors concert classique.) ; (Musique live ; MUSIQUE_LIVE ; Concert ; CONCERT ; Prestation musicale en direct devant un public.) ; (Musique live ; MUSIQUE_LIVE ; Festival de musique ; FESTIVAL_MUSIQUE ; Manifestation rassemblant plusieurs concerts sur un ou plusieurs jours.) ; (Musique live ; MUSIQUE_LIVE ; Livestream musical ; LIVESTREAM_MUSIQUE ; Concert diffusé en direct sur internet.) ; (Pratique artistique ; PRATIQUE_ART ; Abonnement pratique artistique ; ABO_PRATIQUE_ART ; Accès régulier à des cours ou ateliers de création artistique.) ; (Pratique artistique ; PRATIQUE_ART ; Atelier, stage de pratique artistique ; ATELIER_PRATIQUE_ART ; Session ponctuelle d'apprentissage ou de création (dessin, théâtre, danse…).) ; (Pratique artistique ; PRATIQUE_ART ; Séance d'essai ; SEANCE_ESSAI_PRATIQUE_ART ; Première séance gratuite ou à tarif réduit pour découvrir une activité artistique.) ; (Pratique artistique ; PRATIQUE_ART ; Pratique artistique - vente à distance ; PRATIQUE_ART_VENTE_DISTANCE ; Achat de matériel ou inscription à une activité artistique en ligne.) ; (Pratique artistique ; PRATIQUE_ART ; Pratique artistique - Plateforme en ligne ; PLATEFORME_PRATIQUE_ARTISTIQUE ; Site ou application proposant des cours artistiques à distance.) ; (Pratique artistique ; PRATIQUE_ART ; Pratique artistique - livestream ; LIVESTREAM_PRATIQUE_ARTISTIQUE ; Atelier ou cours artistique diffusé en direct.) ; (Spectacle vivant ; SPECTACLE ; Abonnement spectacle ; ABO_SPECTACLE ; Carte ou forfait donnant accès à plusieurs spectacles.) ; (Spectacle vivant ; SPECTACLE ; Festival de spectacle vivant ; FESTIVAL_SPECTACLE ; Évènement regroupant des représentations scéniques (théâtre, danse, cirque…).) ; (Spectacle vivant ; SPECTACLE ; Spectacle, représentation ; SPECTACLE_REPRESENTATION ; Performance en direct sur scène (théâtre, danse, opéra…).) ; (Spectacle vivant ; SPECTACLE ; Spectacle enregistré ; SPECTACLE_ENREGISTRE ; Captation vidéo d'un spectacle diffusée ultérieurement.) ; (Spectacle vivant ; SPECTACLE ; Spectacle vivant - vente à distance ; SPECTACLE_VENTE_DISTANCE ; Achat de billets pour un spectacle en ligne.) ; (Spectacle vivant ; SPECTACLE ; Livestream d'évènement ; LIVESTREAM_EVENEMENT ; Diffusion en direct d'un spectacle sur internet.)

Avec le titre et la description d'une offre, que je vais t'envoyer, tu dois retourner un objet JSON composé uniquement de subcategory_ID.

À noter que le domaine d'activité est le domaine de la culture et des offres culturelles au sens large. Tu utiliseras donc tes connaissances dans les offres culturelles, ainsi que des recherches web, pour trouver systématiquement la bonne sous-catégorie. Il ne t'est pas possible de ne pas proposer de sous-catégorie. Mais tu ne dois pas te tromper ! Assure-toi bien de faire les recherches nécessaires pour ne pas choisir n'importe quoi.

Voici l'offre concernée :

TITRE = "
"""
    if description:
        return prompt + name + descr + description
    return prompt + name + '"'


# HACKATON bdalbianco
"""notes
pip install openapi
pip install openai
pip install google-genai

Version demo : renvoyer sous-categorie (et categ?)
version prod: ne pas renvoyer les infos, les mettre direct en bdd
version cron: stocker en excel? autre bdd? csv?
"""



def core_select_category_auto(name: str, description: str | None) -> dict:
    """this is the core function of the project. First we get the prompt
    Then we set up the model (chatgpt or openai for now)
    then we send the prompt and get the response"""
    #create prompt
    prompt = create_prompt(name, description)

    # if FeatureToggle.WIP_HACKATON_CATEGOTOMATIQUE_USE_CHATGPT:
    # Setup the api
    api_key = os.environ.get("OPENAPI_KEY")
    client = OpenAI(api_key=api_key)
    # get result
    completion = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}])

    # format response
    res = json.loads(completion.choices[0].message.content)
    # res["subcategory_ID"]
    return res
    # elif FeatureToggle.WIP_HACKATON_CATEGOTOMATIQUE_USE_GEMINI:
    # api_key = os.environ.get("GEMINI_API_KEY")
    # client = genai.Client(api_key=api_key)
    # response = client.models.generate_content(
    #     model="gemini-2.0-flash", contents=prompt
    # )
    # print(response.text, response)
    # return {}

def fetch_categories_batch() -> dict:

    query = db.session.query(offers_models.Offer).order_by(offers_models.Offer.id.desc()).limit(5)
    for elem in query:
        res = core_select_category_auto(elem.name, elem.description)["subcategory_ID"]
        elem.subcategoryId = res

        setattr(elem, "subcategoryId", res)
        repository.add_to_session(elem)

    query_bis = db.session.query(offers_models.Offer).order_by(offers_models.Offer.id.desc()).limit(5).all()
    for x in query_bis:
        print(x.subcategoryId)
    return None

@private_api.route("/offers/categories_automatic", methods=["POST"])
# @login_required
# @spectree_serialize(
#     # response_model=offers_serialize.CategoriesResponseModel,
#     response_model=dict(),
#     api=blueprint.pro_private_schema,
# )
# @atomic()
def fetch_categories_auto() -> dict:
    """route function"""
    # if FeatureToggle.WIP_HACKATON_CATEGOTOMATIQUE_AUTOMATICALLY_ASSIGN_OFFER_CATEGORY:

    # Get data from request
    data = request.get_json()
    name = data.get("name")
    description = data.get("description")
    # return core_select_category_auto(name, description)

    """batch prototype function"""
    # fetch_categories_batch()

    """prod function"""
    core_select_category_auto(name, description)

    return {}




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
