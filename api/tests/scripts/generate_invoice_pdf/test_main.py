import logging
from unittest.mock import patch

from pcapi.core.finance import factories as finance_factories
from pcapi.core.finance import models as finance_models
from pcapi.core.offerers import factories as offerers_factories
from pcapi.core.testing import override_settings
from pcapi.scripts.generate_invoice_pdf.main import generate_invoice_pdf


def test_run(caplog, app, css_font_http_request_mock, clean_database):
    venue = offerers_factories.VenueFactory()
    bank_account = finance_factories.BankAccountFactory(offerer=venue.managingOfferer)
    batch = finance_factories.CashflowBatchFactory()
    cashflows = finance_factories.CashflowFactory.create_batch(
        size=3,
        batch=batch,
        bankAccount=bank_account,
        status=finance_models.CashflowStatus.UNDER_REVIEW,
    )
    offerers_factories.VenueBankAccountLinkFactory(venue=venue, bankAccount=bank_account)
    invoice = finance_factories.InvoiceFactory(cashflows=cashflows, bankAccountId=bank_account.id)

    caplog.clear()
    with caplog.at_level(logging.INFO):
        generate_invoice_pdf(invoice.id)
        assert "Generated invoice HTML" in caplog.text
        assert "Sent invoice" in caplog.text
