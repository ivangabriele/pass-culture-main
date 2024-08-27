from pcapi.core.bookings import exceptions as bookings_exceptions
from pcapi.core.educational import exceptions
from pcapi.core.educational.api import booking as booking_api
from pcapi.models.api_errors import ApiErrors
from pcapi.routes.adage.v1.serialization import constants
from pcapi.routes.public import blueprints
from pcapi.routes.public import spectree_schemas
from pcapi.routes.public.collective.endpoints.simulate_adage_steps import utils
from pcapi.routes.public.collective.serialization.simulate_adage_steps import serialization
from pcapi.routes.public.documentation_constants import http_responses
from pcapi.routes.public.documentation_constants import tags
from pcapi.serialization.decorator import spectree_serialize
from pcapi.serialization.spec_tree import ExtendResponse as SpectreeResponse
from pcapi.validation.routes.users_authentifications import api_key_required


@blueprints.public_api.route("/v2/collective/bookings/<int:booking_id>/confirm", methods=["POST"])
@api_key_required
@spectree_serialize(
    api=spectree_schemas.public_api_schema,
    on_success_status=204,
    tags=[tags.COLLECTIVE_OFFERS],
    resp=SpectreeResponse(
        **(
            http_responses.HTTP_204_COLLECTIVE_BOOKING_STATUS_UPDATE
            | http_responses.HTTP_40X_SHARED_BY_API_ENDPOINTS
            | http_responses.HTTP_403_COLLECTIVE_BOOKING_STATUS_UPDATE_REFUSED
            | http_responses.HTTP_404_COLLECTIVE_OFFER_NOT_FOUND
        )
    ),
)
@utils.exclude_prod_environments
def confirm_collective_booking(booking_id: int, body: serialization.AdageId) -> None:
    """
    Confirm collective booking, like a teacher would within the Adage
    application: the action will be done on behalf of this user.

    Warning: not available for production nor integration environments
    """
    try:
        booking_api.confirm_collective_booking(booking_id)
    except exceptions.InsufficientFund:
        raise ApiErrors({"code": "INSUFFICIENT_FUND"}, status_code=403)
    except exceptions.InsufficientMinistryFund:
        raise ApiErrors({"code": "INSUFFICIENT_MINISTRY_FUND"}, status_code=403)
    except exceptions.InsufficientTemporaryFund:
        raise ApiErrors({"code": "INSUFFICIENT_FUND_DEPOSIT_NOT_FINAL"}, status_code=403)
    except exceptions.BookingIsCancelled:
        raise ApiErrors({"code": "EDUCATIONAL_BOOKING_IS_CANCELLED"}, status_code=403)
    except bookings_exceptions.ConfirmationLimitDateHasPassed:
        raise ApiErrors({"code": "CONFIRMATION_LIMIT_DATE_HAS_PASSED"}, status_code=403)
    except exceptions.EducationalBookingNotFound:
        raise ApiErrors({"code": constants.EDUCATIONAL_BOOKING_NOT_FOUND}, status_code=404)
    except exceptions.EducationalDepositNotFound:
        raise ApiErrors({"code": "DEPOSIT_NOT_FOUND"}, status_code=404)
