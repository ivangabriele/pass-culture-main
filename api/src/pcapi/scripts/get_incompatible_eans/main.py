from .data import eans
from .eans_1_invalid import eans as eans_1_invalid
from .eans_2_invalid import eans as eans_2_invalid
from .eans_3_invalid import eans as eans_3_invalid
from .eans_4_invalid import eans as eans_4_invalid
from .eans_5_invalid import eans as eans_5_invalid
from .eans_6_invalid import eans as eans_6_invalid
from .eans_7_invalid import eans as eans_7_invalid
from .eans_8_invalid import eans as eans_8_invalid
from pcapi.core.offers import models as offers_models


def read_and_split() -> None:
    lines_count_per_file = 5000
    path = "./src/pcapi/scripts/get_incompatible_eans/eans.txt"
    file_number = 0
    lines_count = 0
    result_file_path = f"./src/pcapi/scripts/get_incompatible_eans/eans_{file_number}.py"

    with open(path, "r") as file:

        for line in file:
            if lines_count % lines_count_per_file == 0:
                with open(result_file_path, "a") as result_file:
                    result_file.write("}")

                file_number += 1
                result_file_path = f"./src/pcapi/scripts/get_incompatible_eans/eans_{file_number}.py"

                with open(result_file_path, "a") as result_file:
                    result_file.write("eans = {\n")

            with open(result_file_path, "a") as result_file:
                result_file.write(f'    "{line.strip()}",\n')

            lines_count += 1


def merge_invalid_eans() -> None:
    eans = set()
    eans.update(eans_1_invalid)
    eans.update(eans_2_invalid)
    eans.update(eans_3_invalid)
    eans.update(eans_4_invalid)
    eans.update(eans_5_invalid)
    eans.update(eans_6_invalid)
    eans.update(eans_7_invalid)
    eans.update(eans_8_invalid)

    path = "./src/pcapi/scripts/get_incompatible_eans/eans_invalid.py"
    with open(path, "a") as result_file:
        result_file.write("eans = {\n")
        for ean in eans:
            result_file.write(f'    "{ean}",\n')


def main(eans_list: set[int]) -> list[int]:
    base_query = offers_models.Product.query.filter(
        offers_models.Product.idAtProviders.in_(eans_list),
        offers_models.Product.gcuCompatibilityType == offers_models.GcuCompatibilityType.COMPATIBLE,
    ).with_entities(offers_models.Product.idAtProviders)
    valid_eans_count = base_query.count()
    invalid_eans = eans_list - set([ean for ean, in base_query.all()])

    print(f"Invalid count: {len(eans_list) - valid_eans_count}")

    print("INVALID EANS : ")
    print(invalid_eans)
