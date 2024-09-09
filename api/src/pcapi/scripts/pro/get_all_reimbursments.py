import datetime

import sqlalchemy as sqla

from pcapi.core.finance import models as finance_models
from pcapi.core.offerers import models as offerer_models
from pcapi.core.users import models as user_models
from pcapi.routes.serialization.reimbursement_csv_serialize import find_reimbursement_details_by_invoices
from pcapi.routes.serialization.reimbursement_csv_serialize import generate_reimbursement_details_csv


def _get_all_invoices(user_id):
    invoices = (
        finance_models.Invoice.query.join(finance_models.Invoice.bankAccount)
        .join(finance_models.BankAccount.offerer)
        .join(offerer_models.UserOfferer, offerer_models.UserOfferer.offererId == offerer_models.Offerer.id)
        .filter(
            offerer_models.Offerer.isActive.is_(True),
            offerer_models.UserOfferer.userId == user_id,
            sqla.not_(offerer_models.UserOfferer.isRejected) & sqla.not_(offerer_models.UserOfferer.isDeleted),
            offerer_models.UserOfferer.isValidated.is_(True),
            finance_models.BankAccount.isActive.is_(True),
            finance_models.Invoice.date > datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=10),
        )
    ).all()
    # invoices = invoices.order_by(finance_models.Invoice.date.desc()) ??

    return invoices


def concatenation_csv(user_id):
    invoices = _get_all_invoices(user_id)

    if len(invoices) == 0:
        return

    reimbursement_details = find_reimbursement_details_by_invoices([invoice.reference for invoice in invoices])
    reimbursement_details_csv = generate_reimbursement_details_csv(reimbursement_details)
    return reimbursement_details_csv
    # reimbursement_details_csv.encode("utf-8-sig") ????


def main():
    # user_mails = [settings.CGR_USER_MAIL, settings.KINEPOLIS_USER_MAIL] # ecrire les user id dans la config map du repo deployment
    user_mails = ["retention_structures@example.com", "activation@example.com"]
    for user_mail in user_mails:
        user = user_models.User.query.filter_by(email=user_mail).one_or_none()
        reimbursement_details_csv = concatenation_csv(user.id)
        # lien_du_bucket = ecrire_dans_un_bucket(ultimate_csv)
        # store_public_object(
        #     folder="invoices", object_id=invoice_storage_id, blob=invoice_pdf, content_type="application/pdf"
        # )

        # send_mail(user_id, lien_du_bucket) # nine ?


# ajouter ça dans tasks/workers -> ajouter un job()
# dans generate_invoices() appeler la cloud task
