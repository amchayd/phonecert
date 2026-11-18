"""Apple internal identifiers (ProductType) -> commercial names.
Note: the identifier number is NOT the iPhone generation (iPhone17,1 = iPhone 16 Pro).
"""
MODELS = {
    "iPhone10,1": "iPhone 8", "iPhone10,4": "iPhone 8",
    "iPhone10,2": "iPhone 8 Plus", "iPhone10,5": "iPhone 8 Plus",
    "iPhone10,3": "iPhone X", "iPhone10,6": "iPhone X",
    "iPhone11,2": "iPhone XS", "iPhone11,4": "iPhone XS Max", "iPhone11,6": "iPhone XS Max",
    "iPhone11,8": "iPhone XR",
    "iPhone12,1": "iPhone 11", "iPhone12,3": "iPhone 11 Pro", "iPhone12,5": "iPhone 11 Pro Max",
    "iPhone12,8": "iPhone SE (2nd gen)",
    "iPhone13,1": "iPhone 12 mini", "iPhone13,2": "iPhone 12",
    "iPhone13,3": "iPhone 12 Pro", "iPhone13,4": "iPhone 12 Pro Max",
    "iPhone14,4": "iPhone 13 mini", "iPhone14,5": "iPhone 13",
    "iPhone14,2": "iPhone 13 Pro", "iPhone14,3": "iPhone 13 Pro Max",
    "iPhone14,6": "iPhone SE (3rd gen)",
    "iPhone14,7": "iPhone 14", "iPhone14,8": "iPhone 14 Plus",
    "iPhone15,2": "iPhone 14 Pro", "iPhone15,3": "iPhone 14 Pro Max",
    "iPhone15,4": "iPhone 15", "iPhone15,5": "iPhone 15 Plus",
    "iPhone16,1": "iPhone 15 Pro", "iPhone16,2": "iPhone 15 Pro Max",
    "iPhone17,1": "iPhone 16 Pro", "iPhone17,2": "iPhone 16 Pro Max",
    "iPhone17,3": "iPhone 16", "iPhone17,4": "iPhone 16 Plus", "iPhone17,5": "iPhone 16e",
    "iPhone18,1": "iPhone 17 Pro", "iPhone18,2": "iPhone 17 Pro Max",
    "iPhone18,3": "iPhone 17", "iPhone18,4": "iPhone Air",
}


# Year Apple released each ProductType — needed to resolve the single year digit in old-format serials.
RELEASE_YEAR = {
    "iPhone10,1": 2017, "iPhone10,4": 2017, "iPhone10,2": 2017, "iPhone10,5": 2017,
    "iPhone10,3": 2017, "iPhone10,6": 2017,
    "iPhone11,2": 2018, "iPhone11,4": 2018, "iPhone11,6": 2018, "iPhone11,8": 2018,
    "iPhone12,1": 2019, "iPhone12,3": 2019, "iPhone12,5": 2019, "iPhone12,8": 2020,
    "iPhone13,1": 2020, "iPhone13,2": 2020, "iPhone13,3": 2020, "iPhone13,4": 2020,
    "iPhone14,4": 2021, "iPhone14,5": 2021, "iPhone14,2": 2021, "iPhone14,3": 2021,
    "iPhone14,6": 2022, "iPhone14,7": 2022, "iPhone14,8": 2022,
    "iPhone15,2": 2022, "iPhone15,3": 2022, "iPhone15,4": 2023, "iPhone15,5": 2023,
    "iPhone16,1": 2023, "iPhone16,2": 2023,
    "iPhone17,1": 2024, "iPhone17,2": 2024, "iPhone17,3": 2024, "iPhone17,4": 2024, "iPhone17,5": 2025,
    "iPhone18,1": 2025, "iPhone18,2": 2025, "iPhone18,3": 2025, "iPhone18,4": 2025,
}


def release_year(product_type):
    return RELEASE_YEAR.get(product_type or "")


def model_name(product_type):
    return MODELS.get(product_type or "", f"Unknown model ({product_type})")
