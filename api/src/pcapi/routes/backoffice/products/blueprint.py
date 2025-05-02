import dataclasses
import enum

from flask import flash
from flask import render_template
from flask import request
from flask import url_for
from flask_login import current_user
from markupsafe import Markup
from werkzeug.exceptions import NotFound
from werkzeug.utils import redirect

from pcapi.core.offers import api as offers_api
from pcapi.core.offers import models as offers_models
from pcapi.core.permissions import models as perm_models
from pcapi.models import db
from pcapi.models.offer_mixin import OfferValidationStatus
from pcapi.repository.session_management import mark_transaction_as_invalid
from pcapi.routes.backoffice import utils
from pcapi.utils import requests

from . import forms


list_products_blueprint = utils.child_backoffice_blueprint(
    "product",
    __name__,
    url_prefix="/pro/product",
    permission=perm_models.Permissions.READ_OFFERS,
)


class ProductDetailsActionType(enum.StrEnum):
    WHITELIST = enum.auto()
    BLACKLIST = enum.auto()


@dataclasses.dataclass
class ProductDetailsAction:
    type: ProductDetailsActionType
    position: int
    inline: bool


class ProductDetailsActions:
    def __init__(self, threshold: int) -> None:
        self.current_pos = 0
        self.actions: list[ProductDetailsAction] = []
        self.threshold = threshold

    def add_action(self, action_type: ProductDetailsActionType) -> None:
        self.actions.append(
            ProductDetailsAction(type=action_type, position=self.current_pos, inline=self.current_pos < self.threshold)
        )
        self.current_pos += 1

    def __contains__(self, action_type: ProductDetailsActionType) -> bool:
        return action_type in [e.type for e in self.actions]

    @property
    def inline_actions(self) -> list[ProductDetailsActionType]:
        return [action.type for action in self.actions if action.inline]

    @property
    def additional_actions(self) -> list[ProductDetailsActionType]:
        return [action.type for action in self.actions if not action.inline]


def _get_product_details_actions(product: offers_models.Product, threshold: int) -> ProductDetailsAction:
    product_details_actions = ProductDetailsActions(threshold)
    if utils.has_current_user_permission(perm_models.Permissions.PRO_FRAUD_ACTIONS):
        product_details_actions.add_action(ProductDetailsActionType.WHITELIST)
        product_details_actions.add_action(ProductDetailsActionType.BLACKLIST)

    ############################################################################################################
    # Caution !!! EDIT_VENUE and MOVE actions are added in get_offer_details to avoid duplicated stock queries #
    ############################################################################################################

    return product_details_actions


@list_products_blueprint.route("/<int:product_id>", methods=["GET"])
@utils.permission_required(perm_models.Permissions.READ_OFFERS)
def get_product_details(product_id: int) -> utils.BackofficeResponse:
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    print("ca refait la requetes a chaque fois :skull:")
    product = offers_models.Product.query.get(product_id)
    offer_not_linked = db.session.query(offers_models.Offer).filter_by(ean=product.ean).paginate(page, per_page, False)
    print("???", offer_not_linked.__dict__)
    if not product:
        raise NotFound()

    # editable_stock_ids = set()
    # if product.isEvent and not finance_api.are_cashflows_being_generated():
    #     # store the ids in a set as we will use multiple in on it
    #     editable_stock_ids = _get_editable_stock(product_id)
    #
    # is_advanced_pro_support = utils.has_current_user_permission(perm_models.Permissions.ADVANCED_PRO_SUPPORT)
    # # if the actions count is above this threshold then display the action buttons in a dropdown menu
    allowed_actions = _get_product_details_actions(product, threshold=4)

    # edit_product_venue_form = None
    # if is_advanced_pro_support:
    #     try:
    #         venue_choices = products_api.check_can_move_event_product(product)
    #         edit_product_venue_form = forms.EditOfferVenueForm()
    #         edit_product_venue_form.set_venue_choices(venue_choices)
    #         # add the action here to avoid additional stock queries
    #         allowed_actions.add_action(OfferDetailsActionType.EDIT_VENUE)
    #     except products_exceptions.MoveOfferBaseException:
    #         pass
    #
    # move_product_form = None
    # if FeatureToggle.MOVE_OFFER_TEST.is_active():
    #     try:
    #         venue_choices = products_api.check_can_move_product(product)
    #         move_product_form = forms.EditOfferVenueForm()
    #         move_product_form.set_venue_choices(venue_choices)
    #         # add the action here to avoid additional stock queries
    #         allowed_actions.add_action(OfferDetailsActionType.MOVE)
    #     except products_exceptions.MoveOfferBaseException:
    #         pass
    #
    # connect_as = get_connect_as(
    #     object_id=product.id,
    #     object_type="product",
    #     pc_pro_path=urls.build_pc_pro_product_path(product),
    # )

    active_offers_count = sum(offer.isActive for offer in product.offers)
    approved_active_offers_count = sum(
        offer.validation == OfferValidationStatus.APPROVED and offer.isActive for offer in product.offers
    )
    approved_inactive_offers_count = sum(
        offer.validation == OfferValidationStatus.APPROVED and not offer.isActive for offer in product.offers
    )
    pending_offers_count = sum(offer.validation == OfferValidationStatus.PENDING for offer in product.offers)
    rejected_offers_count = sum(offer.validation == OfferValidationStatus.REJECTED for offer in product.offers)

    # PRO_FRAUD_ACTIONS
    return render_template(
        # "products/details.html",
        "products/details.html",
        product=product,
        # active_tab=request.args.get("active_tab", "stock"),
        # editable_stock_ids=editable_stock_ids,
        # reindex_product_form=empty_forms.EmptyForm() if is_advanced_pro_support else None,
        # edit_product_venue_form=edit_product_venue_form,
        # move_product_form=move_product_form,
        # connect_as=connect_as,
        provider_name=product.lastProvider.name if product.lastProvider else None,
        offers_count=len(product.offers),
        active_offers_count=active_offers_count,
        approved_active_offers_count=approved_active_offers_count,
        approved_inactive_offers_count=approved_inactive_offers_count,
        pending_offers_count=pending_offers_count,
        rejected_offers_count=rejected_offers_count,
        allowed_actions=allowed_actions,
        action=ProductDetailsActionType,
        offer_not_linked=offer_not_linked.items,
        total_pages=offer_not_linked.pages,
        page=page,
        per_page=per_page,
    )


@list_products_blueprint.route("/<int:product_id>/synchro_titelive", methods=["GET"])
@utils.permission_required(perm_models.Permissions.PRO_FRAUD_ACTIONS)
def get_product_synchro_with_titelive_form(product_id: int) -> utils.BackofficeResponse:

    product = offers_models.Product.query.filter_by(id=product_id).one_or_none()
    if not product:
        raise NotFound()

    return render_template(
        "components/turbo/modal_form.html",
        form=empty_forms.EmptyForm(),
        dst=url_for("backoffice_web.product.shynchro_product_with_titelive", product_id=product.id),
        div_id=f"synchro-product-modal-{product.id}",
        title=f"Synchroniser le produit  {product.name} avec Titelive",
        button_text="Synchroniser le produit",
    )


@list_products_blueprint.route("/<int:product_id>/synchro-titelive", methods=["POST"])
@utils.permission_required(perm_models.Permissions.PRO_FRAUD_ACTIONS)
def shynchro_product_with_titelive(product_id: int) -> utils.BackofficeResponse:
    product = offers_models.Product.query.filter_by(id=product_id).one_or_none()

    try:
        # titelive_product = offers_api.get_new_product_from_ean13(product.ean)
        # product = offers_api.fetch_or_update_product_with_titelive_data(titelive_product)
        offers_api.whitelist_product(product.ean)
    except requests.ExternalAPIException as err:
        mark_transaction_as_invalid()
        flash(
            Markup("Une erreur s'est produite : {message}").format(message=str(err) or err.__class__.__name__),
            "warning",
        )
    else:
        flash("Le produit a été Synchroniser avec Titelive", "success")

    return redirect(request.referrer, 303)
    # return redirect(request.referrer or url_for("backoffice_web.product.list_offers"), 303)


@list_products_blueprint.route("/<int:product_id>/blacklist", methods=["GET"])
@utils.permission_required(perm_models.Permissions.PRO_FRAUD_ACTIONS)
def get_product_blacklist_form(product_id: int) -> utils.BackofficeResponse:
    product = offers_models.Product.query.filter_by(id=product_id).one_or_none()
    if not product:
        raise NotFound()

    form = empty_forms.EmptyForm()
    return render_template(
        "components/turbo/modal_form.html",
        form=form,
        dst=url_for("backoffice_web.product.blacklist_product", product_id=product.id),
        div_id=f"blacklist-product-modal-{product.id}",
        title=f"Blacklisté le produit  {product.name}",
        button_text="Blacklisté le produit",
    )


@list_products_blueprint.route("/<int:product_id>/blacklist", methods=["POST"])
@utils.permission_required(perm_models.Permissions.PRO_FRAUD_ACTIONS)
def blacklist_product(product_id: int) -> utils.BackofficeResponse:
    print("ALORS")
    product = offers_models.Product.query.filter_by(id=product_id).one_or_none()

    if offers_api.reject_inappropriate_products([product.ean], current_user, rejected_by_fraud_action=True):
        db.session.commit()
        flash("Le produit a été rendu incompatible aux CGU et les offres ont été désactivées", "success")
    else:
        db.session.rollback()
        flash("Une erreur s'est produite lors de l'opération", "warning")

    return redirect(request.referrer, 303)

    # # function qui blacklist
    # flash("Le produit a été blacklisté", "success")
    # return redirect(request.referrer, 303)
    # # return redirect(request.referrer or url_for("backoffice_web.product.list_offers"), 303)


# @list_products_blueprint.route("/<int:product_id>/batch-link-offer-to-product-form", methods=["GET", "POST"])
@list_products_blueprint.route("/<int:product_id>/link_offers/confirm", methods=["GET", "POST"])
@utils.permission_required(perm_models.Permissions.PRO_FRAUD_ACTIONS)
def confirm_link_offers_forms(product_id: int) -> utils.BackofficeResponse:
    form = forms.BatchLinkOfferToProductForm()
    if form.object_ids.data:
        pass
    print("OUI")
    return render_template(
        "components/turbo/modal_form.html",
        form=form,
        dst=url_for("backoffice_web.product.batch_link_offers_to_product", product_id=product_id),
        div_id="batch-link-to-product-modal",
        title=Markup("Voulez-vous associé ces {number_of_offers} offre au produit ?").format(
            number_of_offers=len(form.object_ids_list)
        ),
        button_text="Confirmer l'association",
        information=Markup("Vous allez associer {number_of_offers} offre(s). Voulez vous continuer ?").format(
            number_of_offers=len(form.object_ids_list),
        ),
    )


@list_products_blueprint.route("/<int:product_id>/link_offers", methods=["POST"])
@utils.permission_required(perm_models.Permissions.PRO_FRAUD_ACTIONS)
def batch_link_offers_to_product(product_id) -> utils.BackofficeResponse:
    form = forms.BatchLinkOfferToProductForm()
    offers = db.session.query(offers_models.Offer).filter(offers_models.Offer.id.in_(form.object_ids_list)).all()
    for offer in offers:
        offer.productId = product_id
    return redirect(request.referrer or url_for(".get_product_details", product_id=product_id), 303)
