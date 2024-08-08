class CreateProductError(Exception):
    msg = "can't create this offer"


class CreateProductDBError(CreateProductError):
    msg = "internal error, can't create this offer"


class ExistingVenueWithIdAtProviderError(CreateProductDBError):
    msg = "`idAtProvider` already exists for this venue, can't create this offer"


class CreateStockError(CreateProductError):
    pass


class CreateStockDBError(CreateStockError):
    pass
