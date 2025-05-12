import dataclasses
import enum

import pydantic.v1 as pydantic_v1
import sqlalchemy.orm as sa_orm
from flask import flash
from flask import render_template
from flask import request
from flask import url_for
from flask_login import current_user
from markupsafe import Markup
from werkzeug.exceptions import NotFound
from werkzeug.utils import redirect

import pcapi.core.fraud.models as fraud_models
from pcapi.connectors.serialization import titelive_serializers
from pcapi.connectors.titelive import get_by_ean13
from pcapi.core.offerers import models as offerers_models
from pcapi.core.offers import api as offers_api
from pcapi.core.offers import models as offers_models
from pcapi.core.permissions import models as perm_models
from pcapi.core.providers.titelive_book_search import get_ineligibility_reason
from pcapi.core.users import models as users_models
from pcapi.models import db
from pcapi.models.offer_mixin import OfferValidationStatus
from pcapi.repository.session_management import mark_transaction_as_invalid
from pcapi.routes.backoffice import utils
from pcapi.routes.backoffice.forms import empty as empty_forms
from pcapi.routes.backoffice.offers.serializer import OfferSerializer
from pcapi.utils import requests
from . import forms

list_products_blueprint = utils.child_backoffice_blueprint(
    "product",
    __name__,
    url_prefix="/pro/product",
    permission=perm_models.Permissions.READ_OFFERS,
)

fake_titelive_response = {
    "type": 1,
    "magid": "6505",
    "compatibility": [],
    "oeuvre": {
        "id": "1072422",
        "titre": "Immortelle randonnée ; Compostelle malgré moi",
        "auteurs": "Jean-Christophe Rufin",
        "auteurs_multi": {"10078": "Jean-Christophe Rufin"},
        "auteurs_id": ["10078"],
        "auteurs_fonctions": [],
        "realisateur_multi": [],
        "article": [
            {
                "nombre": 0,
                "gencod": "9782070455379",
                "id_catalogue": ["0"],
                "collection": "Folio",
                "collection_no": "5833",
                "editeur": "FOLIO",
                "distributeur": "SODIS",
                "code_distributeur": "21",
                "prix": 8.3,
                "prixpays": {
                    "fr": {"value": 8.3, "devise": "&euro;"},
                    "be": {"value": 8.3, "devise": "&euro;"},
                    "ch": {"value": 14, "devise": "CHF"},
                },
                "dateparution": "02/10/2014",
                "dateparutionentier": 1412200800,
                "dispo": 1,
                "dispopays": {"fr": 1, "be": 1, "ch": 1},
                "libelledispo": "Disponible",
                "resume": "Un mois sur le Camino del Norte, de Bayonne à Santiago, 40 kilomètres de marche par jour : étape après étape, Jean-Christophe Rufin se transforme en clochard céleste, en routard de Compostelle. Pourquoi prendre le Chemin, quand on a déjà éprouvé toutes les marches, toutes les aventures physiques ? \" Je n'avais en réalité pas eu le choix. Le virus de Saint-Jacques m'avait profondément infecté. J'ignore par qui et par quoi s'est opérée la contagion. \r\nMais, après une phase d'incubation silencieuse, la maladie avait éclaté, et j'en avais tous les symptômes. \" 876 kilomètres plus loin, un mois plus tard, après l'arrivée à Santiago, le constat est là. Comme tous les grands pèlerinages, le Chemin est une expérience de désincarnation, il libère du \" tropplein \", mais il est aussi un itinéraire spirituel, entre cathédrales et ermitages, et humain, car chaque rencontre y prend une résonance particulière.\r",
                "image": "1",
                "image_spe": "1",
                "image_alkor": 0,
                "image_4": "1",
                "imagesUrl": {
                    "recto": "https://images.epagine.fr/379/9782070455379_1_75.jpg",
                    "vign": "https://images.epagine.fr/379/9782070455379_1_v.jpg",
                    "moyen": "https://images.epagine.fr/379/9782070455379_1_m.jpg",
                    "verso": "https://images.epagine.fr/379/9782070455379_4_75.jpg",
                },
                "detailUrl": "/livre/9782070455379-immortelle-randonnee-compostelle-malgre-moi-jean-christophe-rufin/",
                "langue": "Français",
                "langueiso": "fra",
                "langueflag": "https://static.epagine.fr/commonfiles/flags/fr.png",
                "nbmag": "540",
                "codesupport": "P",
                "libellesupport": "Poche",
                "codesupport2": [],
                "libellesupport2": [],
                "chapitre": 0,
                "biblio": "0",
                "extrait": 0,
                "extrait_oeuvre": "1",
                "pages": "288",
                "longueur": 17.8,
                "largeur": 10.8,
                "hauteur": 0,
                "epaisseur": 1.8,
                "poids": "180",
                "biographie": "1",
                "biographies": [],
                "websites": [],
                "datecreation": "23/05/2014",
                "datecreationentier": 1400796000,
                "datemodification": "03/01/2024",
                "serie": "Non précisée",
                "idserie": "0",
                "scolaire": "0",
                "livre_etranger": "0",
                "racine_editeur": "207",
                "code_clil": "3665",
                "type_prix": "4",
                "contenu_explicite": 0,
                "nb_galettes": 0,
                "duree": 0,
                "anneesortie": 0,
                "interpretes": [],
                "typeproduit": 0,
                "colors": [],
                "langues": [],
                "audios": [],
                "soustitres": [],
                "iad": "0",
                "id_code_langue": "10000",
                "taux_tva": "5.50",
                "code_tva": "2",
                "nboccasions": 0,
                "stock": 0,
                "gtl": {
                    "first": {
                        "1": {"code": "1000000", "libelle": "Litt&eacute;rature"},
                        "2": {"code": "1050000", "libelle": "R&eacute;cit"},
                    }
                },
                "gtlvideo": [],
                "operations": [],
                "tracks": [],
                "cmb": "110206",
                "deee_ht": 0,
                "tva": 0,
                "minutesdejeu": 0,
                "nbjoueursmin": 0,
                "nbjoueursmax": 0,
                "colisage": 0,
                "longueurboite": 0,
                "largeurboite": 0,
                "hauteurboite": 0,
                "grammesboite": 0,
                "nbpiles": 0,
                "pilesincluses": 0,
                "nbanneegarantie": 0,
                "produits_recycles": 0,
                "nbpages": 0,
                "grammage": 0,
                "taille_ecriture_mm": 0,
                "poignee": 0,
                "lavable": 0,
                "impermeable": 0,
                "contenance_ml": 0,
                "nbfeuilles": 0,
                "diametre": 0,
                "diametreboite": 0,
                "garantiemois": 0,
                "precommande": 0,
                "ispromotion": 0,
                "isnew": 0,
                "multijoueur": 0,
                "nblicenses": 0,
                "nbutilisateur": 0,
                "internet": 0,
                "pegi": [],
                "solo": 0,
                "online": 0,
                "avertissement": [],
                "drmlcp": 0,
                "bonus_extraits": {
                    "gencod": "9782070455379",
                    "pagesinterieures": "0",
                    "pdfextrait": "0",
                    "pdfchapitre": "0",
                    "pdfparagraphe": "0",
                    "mp3_count": "0",
                },
                "id_lectorat": "0",
                "livre_lu": "0",
                "grands_caracteres": "0",
                "multilingue": "0",
                "illustre": "0",
                "luxe": "0",
                "relie": "0",
                "broche": "1",
                "lectureEnLigne": 0,
                "NombreMagasins": 0,
                "collector": "0",
                "code_editeur": "27818",
                "sorecop": 0,
                "pcb": 0,
                "spcb": 0,
                "volume": 0,
                "compartiment": 0,
                "poche": 0,
            }
        ],
        "biographies": [],
        "websites": [],
        "typeproduit": 0,
    },
    "ean": "9782070455379",
    "changeEncodingTo": "UTF-8",
    "extraparams": {"ws": 1},
}
INELIGIBLE_BOOK_BY_EAN_FIXTURE = {
    "type": 1,
    "magid": "6505",
    "compatibility": [],
    "oeuvre": {
        "id": "3869601",
        "titre": "Annales ABC du bac ; sujets & corrig\u00e9s : math\u00e9matiques ; terminale (\u00e9dition 2024)",
        "auteurs": "Julien Besson, Isabelle Lericque, Luis Mateus, Jo\u00ebl Ternoy",
        "auteurs_multi": {
            "356832": "Julien Besson",
            "356833": "Luis Mateus",
            "414043": "Isabelle Lericque",
            "414044": "Jo\u00ebl Ternoy",
        },
        "auteurs_id": ["356832", "414043", "356833", "414044"],
        "auteurs_fonctions": [],
        "article": [
            {
                "nombre": 0,
                "gencod": "9782095023584",
                "id_catalogue": ["0"],
                "collection": "Annales Abc Du Bac ; Sujets & Corriges",
                "collection_no": "0",
                "editeur": "Nathan",
                "distributeur": "Interforum",
                "code_distributeur": "371",
                "prix": 8.9,
                "taux_tva": "5.50",
                "code_tva": 2,
                "prixpays": {
                    "fr": {"value": 8.9, "devise": "&euro;"},
                    "be": {"value": 8.9, "devise": "&euro;"},
                    "ch": {"value": 14.6, "devise": "CHF"},
                },
                "dateparution": "24/08/2023",
                "dateparutionentier": 1692828000,
                "datecreation": "19/04/2023",
                "datecreationentier": 1681855200,
                "datemodification": "30/05/2024",
                "dispo": 1,
                "dispopays": {"fr": 1, "be": 1, "ch": 1},
                "libelledispo": "Disponible",
                "resume": "Les Annales ABC du BAC pour r\u00e9viser et pr\u00e9parer l'\u00e9preuve de Math\u00e9matiques Terminale du Bac 2024.\r\n-  30 sujets corrig\u00e9s pour pr\u00e9parer l'\u00e9preuve et le Grand oral.\r\n-  Des fiches de r\u00e9visions pour retenir l'essentiel.\r\n-  Des exercices pour contr\u00f4ler ses connaissances.\r\n-  Des aides pas \u00e0 pas et la m\u00e9thode en contexte + R\u00e9dig\u00e9 par des enseignants ! + Annales ABC du BAC 2024 Math\u00e9matiques Terminale - Enseignement de sp\u00e9cialit\u00e9 Conforme aux programmes du Bac Une nouvelle formule pour pr\u00e9parer avec succ\u00e8s l'\u00e9preuve finale du nouveau Bac !\r\nLes \u00e9preuves du nouveau Bac expliqu\u00e9es.\r\nLes bonnes m\u00e9thodes \u00e0 acqu\u00e9rir pour r\u00e9ussir.\r\nDes rappels de cours, des QCM et des exercices pour faire le point.\r\nDes sujets pas \u00e0 pas avec des corrig\u00e9s expliqu\u00e9s.\r\nDes sujets de Bac comme \u00e0 l'examen pour s'exercer.\r\nUn cahier sp\u00e9cial Grand oral.",
                "image": 1,
                "image_spe": 1,
                "image_4": 0,
                "imagesUrl": {
                    "recto": "https://images.epagine.fr/584/9782095023584_1_75.jpg",
                    "vign": "https://images.epagine.fr/584/9782095023584_1_v.jpg",
                    "moyen": "https://images.epagine.fr/584/9782095023584_1_m.jpg",
                    "verso": "https://images.epagine.fr/is/6505/9782095023584_4_75.jpg",
                },
                "detailUrl": "/livre/9782095023584-annales-abc-du-bac-sujets-corriges-mathematiques-terminale-edition-2024-julien-besson-isabelle-lericque-luis-mateus-joel-ternoy/",
                "langue": "Fran\u00e7ais",
                "langueiso": "fra",
                "langueflag": "https://static.epagine.fr/commonfiles/flags/fr.png",
                "nbmag": 183,
                "codesupport": "T",
                "libellesupport": "Grand format",
                "drm": 0,
                "biblio": 0,
                "extrait": 0,
                "extrait_oeuvre": 1,
                "pages": 384,
                "longueur": 21.2,
                "largeur": 14.6,
                "epaisseur": 2.2,
                "poids": 478,
                "biographie": 0,
                "biographies": [],
                "websites": [],
                "serie": "Non pr\u00e9cis\u00e9e",
                "idserie": "0",
                "scolaire": 0,
                "livre_etranger": 0,
                "racine_editeur": "209",
                "code_clil": "3006",
                "type_prix": "0",
                "typeproduit": 0,
                "iad": "0",
                "id_code_langue": "10000",
                "stock": 0,
                "gtl": {
                    "first": {
                        "1": {"code": "12000000", "libelle": "Parascolaire"},
                        "2": {"code": "12090000", "libelle": "Baccalaur&eacute;at g&eacute;n&eacute;ral (annales)"},
                        "3": {"code": "12090400", "libelle": "Math&eacute;matiques"},
                        "4": {"code": "12090418", "libelle": "Terminale Enseignement de Sp&eacute;cialit&eacute;"},
                    }
                },
                "public_averti": 0,
                "replace": ["9782091572758"],
                "precommande": 0,
                "ispromotion": 0,
                "isnew": 0,
                "drmlcp": 0,
                "bonus_extraits": {
                    "gencod": "9782095023584",
                    "pagesinterieures": 0,
                    "pdfextrait": 0,
                    "pdfchapitre": 0,
                    "pdfparagraphe": 0,
                    "mp3_count": 0,
                },
                "id_lectorat": 0,
                "livre_lu": 0,
                "grands_caracteres": 0,
                "multilingue": 0,
                "illustre": 0,
                "luxe": 0,
                "relie": 0,
                "broche": 1,
                "NombreMagasins": 0,
                "collector": 0,
                "code_editeur": "77",
            }
        ],
        "biographies": [],
        "websites": [],
        "typeproduit": 0,
    },
    "ean": "9782095023584",
    "changeEncodingTo": "UTF-8",
    "extraparams": {"ws": 1},
}
NO_RESULT_BY_EAN_FIXTURE = {
    "type": 1,
    "magid": "7",
    "compatibility": [],
    "magOptions": {
        "Data": {
            "MagasinId": "7",
            "MessagerieCommandes": "1",
            "ComboProduits": '{"produits":{"0":{"id":0,"ordre":1,"search":"paper","libelle":"livres"},"1":{"id":1,"ordre":2,"search":"ebook","libelle":"livres_numeriques"},"3":{"id":3,"ordre":3,"search":"dvd","libelle":"dvd"},"4":{"id":4,"ordre":4,"search":"music","libelle":"musique"},"5":{"id":5,"ordre":5,"search":"jouet","libelle":"recherche_jouet"},"6":{"id":6,"ordre":6,"search":"papeterie","libelle":"recherche_papeterie"},"7":{"id":7,"ordre":7,"search":"jeuvideo","libelle":"jeux_video"},"2":{"id":2,"ordre":8,"search":"liseuse","libelle":"liseuses"}},"options":{"tous_produits":{"affichage":2,"search":"all","libelle":"tous_produits"},"tous_livres":{"affichage":1,"search":"allbooks","libelle":"allbooks"},"ebooks_fr":0,"ebooks_gb":0,"ebooks_nl":0,"livres_fr":0}}',
            "TvaEtrangere0": "0",
            "BlocageReimpression": "0",
            "MATOMO": "Matomo",
            "DetailTables": "1",
            "ExtraitsAudio": "0",
            "SEGMENT": "Segment",
        },
        "Keys": [],
        "LibKeys": [],
        "Database": "OAI-PMH",
        "Fields": [],
        "DateFields": [],
        "DefaultFields": [],
        "ReferencedObjects": [],
    },
    "ean": "9782067256018",
    "changeEncodingTo": "UTF-8",
    "extraparams": {"ws": 1},
}


class ProductDetailsActionType(enum.StrEnum):
    SYNCHRO_TITELIVE = enum.auto()
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
        product_details_actions.add_action(ProductDetailsActionType.SYNCHRO_TITELIVE)
        product_details_actions.add_action(ProductDetailsActionType.WHITELIST)
        product_details_actions.add_action(ProductDetailsActionType.BLACKLIST)
    return product_details_actions


@list_products_blueprint.route("/<int:product_id>", methods=["GET"])
@utils.permission_required(perm_models.Permissions.READ_OFFERS)
def get_product_details(product_id: int) -> utils.BackofficeResponse:
    product = (
        db.session.query(offers_models.Product)
        .filter(offers_models.Product.id == product_id)
        .options(
            sa_orm.joinedload(offers_models.Product.offers).options(
                sa_orm.load_only(
                    offers_models.Offer.id,
                    offers_models.Offer.name,
                    offers_models.Offer.dateCreated,
                    offers_models.Offer.isActive,
                    offers_models.Offer.validation,
                ),
                sa_orm.joinedload(offers_models.Offer.stocks).options(
                    sa_orm.load_only(
                        offers_models.Stock.bookingLimitDatetime,
                        offers_models.Stock.beginningDatetime,
                        offers_models.Stock.quantity,
                        offers_models.Stock.dnBookedQuantity,
                        offers_models.Stock.isSoftDeleted,
                    )
                ),
                sa_orm.joinedload(offers_models.Offer.venue).options(
                    sa_orm.load_only(
                        offerers_models.Venue.id,
                        offerers_models.Venue.name,
                    )
                ),
            ),
            sa_orm.joinedload(offers_models.Product.productMediations),
        )
        .one_or_none()
    )

    if not product:
        raise NotFound()

    unlinked_offers = []
    if product.ean:
        unlinked_offers = (
            db.session.query(offers_models.Offer)
            .filter(offers_models.Offer.ean == product.ean, offers_models.Offer.productId.is_(None))
            .options(
                sa_orm.load_only(
                    offers_models.Offer.id,
                    offers_models.Offer.name,
                    offers_models.Offer.dateCreated,
                    offers_models.Offer.isActive,
                    offers_models.Offer.validation,
                ),
                sa_orm.joinedload(offers_models.Offer.stocks).options(
                    sa_orm.load_only(
                        offers_models.Stock.bookingLimitDatetime,
                        offers_models.Stock.beginningDatetime,
                        offers_models.Stock.quantity,
                        offers_models.Stock.dnBookedQuantity,
                        offers_models.Stock.isSoftDeleted,
                    )
                ),
                sa_orm.joinedload(offers_models.Offer.venue).options(
                    sa_orm.load_only(
                        offerers_models.Venue.id,
                        offerers_models.Venue.name,
                    )
                ),
            )
            .order_by(offers_models.Offer.id)
            .all()
        )

    allowed_actions = _get_product_details_actions(product, threshold=4)

    active_offers_count = sum(offer.isActive for offer in product.offers)
    approved_active_offers_count = sum(
        offer.validation == OfferValidationStatus.APPROVED and offer.isActive for offer in product.offers
    )
    approved_inactive_offers_count = sum(
        offer.validation == OfferValidationStatus.APPROVED and not offer.isActive for offer in product.offers
    )
    pending_offers_count = sum(offer.validation == OfferValidationStatus.PENDING for offer in product.offers)
    rejected_offers_count = sum(offer.validation == OfferValidationStatus.REJECTED for offer in product.offers)

    if product.ean:
        try:
            titelive_data = get_by_ean13(product.ean)
            # titelive_data = INELIGIBLE_BOOK_BY_EAN_FIXTURE
        except Exception as err:
            flash(
                Markup("Une erreur s'est produite : {message}").format(message=str(err) or err.__class__.__name__),
                "warning",
            )
        try:
            data = pydantic_v1.parse_obj_as(titelive_serializers.TiteLiveBookWork, titelive_data["oeuvre"])
        except:
            ineligibility_reason = None
        else:
            ineligibility_reason = get_ineligibility_reason(data.article[0], data.titre)

        product_whitelist = (
            db.session.query(fraud_models.ProductWhitelist)
            .filter(fraud_models.ProductWhitelist.ean == product.ean)
            .options(
                sa_orm.load_only(
                    fraud_models.ProductWhitelist.ean,
                    fraud_models.ProductWhitelist.dateCreated,
                    fraud_models.ProductWhitelist.comment,
                    fraud_models.ProductWhitelist.authorId,
                ),
                sa_orm.joinedload(fraud_models.ProductWhitelist.author).load_only(
                    users_models.User.firstName, users_models.User.lastName
                ),
            )
            .one_or_none()
        )
    else:
        titelive_data = None
        ineligibility_reason = None
        product_whitelist = None

    return render_template(
        "products/details.html",
        product=product,
        provider_name=product.lastProvider.name if product.lastProvider else None,
        allowed_actions=allowed_actions,
        action=ProductDetailsActionType,
        product_offers=[OfferSerializer.from_orm(offer).dict() for offer in sorted(product.offers, key=lambda o: o.id)],
        unlinked_offers=[OfferSerializer.from_orm(offer).dict() for offer in unlinked_offers],
        titelive_data=titelive_data,
        active_offers_count=active_offers_count,
        approved_active_offers_count=approved_active_offers_count,
        approved_inactive_offers_count=approved_inactive_offers_count,
        pending_offers_count=pending_offers_count,
        rejected_offers_count=rejected_offers_count,
        ineligibility_reason=ineligibility_reason,
        product_whitelist=product_whitelist,
    )


@list_products_blueprint.route("/<int:product_id>/synchro_titelive", methods=["GET"])
@utils.permission_required(perm_models.Permissions.PRO_FRAUD_ACTIONS)
def get_product_synchro_with_titelive_form(product_id: int) -> utils.BackofficeResponse:

    product = offers_models.Product.query.filter_by(id=product_id).one_or_none()
    if not product:
        raise NotFound()

    try:
        titelive_data = get_by_ean13(product.ean)
        # titelive_data = INELIGIBLE_BOOK_BY_EAN_FIXTURE
    except Exception as err:
        flash(
            Markup("Une erreur s'est produite : {message}").format(message=str(err) or err.__class__.__name__),
            "warning",
        )
    try:
        data = pydantic_v1.parse_obj_as(titelive_serializers.TiteLiveBookWork, titelive_data["oeuvre"])
    except Exception:
        ineligibility_reason = None
    else:
        ineligibility_reason = get_ineligibility_reason(data.article[0], data.titre)

    return render_template(
        "products/titelive_synchro_modal.html",
        form=empty_forms.EmptyForm(),
        dst=url_for(".synchro_product_with_titelive", product_id=product_id, json=fake_titelive_response),
        title="Données récupérer via l'API Titelive",
        titelive_data=titelive_data,
        div_id=f"synchro-product-modal-{product.id}",
        button_text="Mettre le produit à jour avec ces informations",
        ineligibility_reason=ineligibility_reason,
        product_whitelist=None,
    )


@list_products_blueprint.route("/<int:product_id>/synchro-titelive", methods=["POST"])
@utils.permission_required(perm_models.Permissions.PRO_FRAUD_ACTIONS)
def synchro_product_with_titelive(product_id: int) -> utils.BackofficeResponse:
    product = offers_models.Product.query.filter_by(id=product_id).one_or_none()
    if not product:
        raise NotFound()

    try:
        titelive_product = offers_api.get_new_product_from_ean13(product.ean)
        offers_api.fetch_or_update_product_with_titelive_data(titelive_product)
    except requests.ExternalAPIException as err:
        mark_transaction_as_invalid()
        flash(
            Markup("Une erreur s'est produite : {message}").format(message=str(err) or err.__class__.__name__),
            "warning",
        )
    else:
        flash("Le produit a été Synchroniser avec Titelive", "success")

    return redirect(request.referrer or url_for(".get_product_details", product_id=product_id), 303)


@list_products_blueprint.route("/<int:product_id>/whitelist", methods=["GET"])
@utils.permission_required(perm_models.Permissions.PRO_FRAUD_ACTIONS)
def get_product_whitelist_form(product_id: int) -> utils.BackofficeResponse:
    product = offers_models.Product.query.filter_by(id=product_id).one_or_none()
    if not product:
        raise NotFound()

    form = empty_forms.EmptyForm()
    return render_template(
        "components/turbo/modal_form.html",
        form=form,
        dst=url_for("backoffice_web.product.whitelist_product", product_id=product.id),
        div_id=f"whitelist-product-modal-{product.id}",
        title=f"Whitelisté le produit  {product.name}",
        button_text="Whitelisté le produit",
    )


@list_products_blueprint.route("/<int:product_id>/whitelist", methods=["POST"])
@utils.permission_required(perm_models.Permissions.PRO_FRAUD_ACTIONS)
def whitelist_product(product_id: int) -> utils.BackofficeResponse:
    product = offers_models.Product.query.filter_by(id=product_id).one_or_none()
    if not product:
        raise NotFound()

    product.gcuCompatibilityType = offers_models.GcuCompatibilityType.COMPATIBLE
    return redirect(request.referrer or url_for(".get_product_details", product_id=product_id), 303)


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
    product = offers_models.Product.query.filter_by(id=product_id).one_or_none()
    if not product:
        raise NotFound()

    if offers_api.reject_inappropriate_products([product.ean], current_user, rejected_by_fraud_action=True):
        db.session.commit()
        flash("Le produit a été rendu incompatible aux CGU et les offres ont été désactivées", "success")
    else:
        db.session.rollback()
        flash("Une erreur s'est produite lors de l'opération", "warning")

    return redirect(request.referrer or url_for(".get_product_details", product_id=product_id), 303)


@list_products_blueprint.route("/<int:product_id>/link_offers/confirm", methods=["GET", "POST"])
@utils.permission_required(perm_models.Permissions.PRO_FRAUD_ACTIONS)
def confirm_link_offers_forms(product_id: int) -> utils.BackofficeResponse:
    form = forms.BatchLinkOfferToProductForm()

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


def render_search_template(form: forms.ProductSearchForm | None = None) -> str:
    if form is None:
        preferences = current_user.backoffice_profile.preferences
        form = forms.ProductSearchForm()

    return render_template(
        "products/search.html",
        title="Recherche produit",
        dst=url_for(".search_product"),
        form=form,
    )


@list_products_blueprint.route("/search", methods=["GET"])
def search_product() -> utils.BackofficeResponse:
    if not request.args:
        return render_search_template()

    form = forms.ProductSearchForm(request.args)
    if not form.validate():
        return render_search_template(form), 400

    result_type = forms.ProductFilterTypeEnum[form.product_filter_type.data]
    search_query = form.q.data

    product = None
    if result_type == forms.ProductFilterTypeEnum.EAN:
        product = db.session.query(offers_models.Product).filter_by(ean=search_query).one_or_none()
    elif result_type == forms.ProductFilterTypeEnum.VISA:
        product = (
            db.session.query(offers_models.Product)
            .filter(offers_models.Product.extraData["visa"].astext == search_query)
            .one_or_none()
        )
    elif result_type == forms.ProductFilterTypeEnum.ALLOCINE_ID:
        product = (
            db.session.query(offers_models.Product)
            .filter(offers_models.Product.extraData["allocine_id"].astext == search_query)
            .one_or_none()
        )

    if not product:
        raise NotFound()

    return redirect(url_for(".get_product_details", product_id=product.id), 303)
