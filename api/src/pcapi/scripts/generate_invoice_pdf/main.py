import argparse
import logging

from pcapi.core.finance import api as finance_api
from pcapi.core.finance import models as finance_models
from pcapi.core.logging import log_elapsed
import pcapi.core.mails.transactional as transactional_mails
from pcapi.flask_app import app


logger = logging.getLogger(__name__)


def generate_invoice_pdf(invoice_id: int) -> None:
    invoice = finance_models.Invoice.query.get(invoice_id)
    batch = (
        finance_models.CashflowBatch.query.join(finance_models.Cashflow.batch)
        .join(finance_models.Cashflow.invoices)
        .filter(finance_models.Invoice.id == invoice.id)
    ).one()
    log_extra = {"bank_account": invoice.bankAccountId}

    with log_elapsed(logger, "Generated invoice HTML", log_extra):
        invoice_html = finance_api._generate_invoice_html(invoice, batch)
    with log_elapsed(logger, "Generated and stored PDF invoice", log_extra):
        finance_api._store_invoice_pdf(invoice_storage_id=invoice.storage_object_id, invoice_html=invoice_html)
    with log_elapsed(logger, "Sent invoice", log_extra):
        transactional_mails.send_invoice_available_to_pro_email(invoice, batch)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--invoice-id", type=int, required=True)
    args = parser.parse_args()

    with app.app_context():
        generate_invoice_pdf(args.invoice_id)
