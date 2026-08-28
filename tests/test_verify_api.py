from binding.api_model import api_hash_for_dict
from binding.verify_api import validate_api_data


def test_api_validator_requires_canonical_type_views():
    data = {
        "schema_version": 2,
        "module_prefix": "lv",
        "functions": [
            {
                "c_name": "lv_init",
                "python_name": "init",
                "role": "module",
                "parameters": [],
                "return_type": {"kind": "primitive", "name": "void"},
                "return_view": {
                    "python_type": "None",
                    "category": "void",
                    "conversion": "none",
                },
                "available_on": ["micropython", "circuitpython", "cpython"],
                "visibility": "public",
            }
        ],
        "objects": [],
        "structs": [],
        "enums": [],
        "typedefs": [],
        "variables": [],
        "constants": [],
    }
    data["api_hash"] = api_hash_for_dict(data)

    assert validate_api_data(data) == []

    del data["functions"][0]["return_view"]
    data["api_hash"] = api_hash_for_dict(data)
    errors = validate_api_data(data)
    assert "function lv_init return view must be an object" in errors


def test_api_validator_checks_view_shapes():
    data = {
        "schema_version": 2,
        "module_prefix": "lv",
        "functions": [],
        "objects": [],
        "structs": [
            {
                "python_name": "point_t",
                "fields": [
                    {
                        "name": "x",
                        "view": {
                            "python_type": "int",
                            "category": "scalar",
                            "conversion": "integer",
                            "nullable": "no",
                        },
                    }
                ],
                "available_on": ["micropython", "circuitpython", "cpython"],
                "visibility": "public",
            }
        ],
        "enums": [],
        "typedefs": [],
        "variables": [],
        "constants": [],
    }
    data["api_hash"] = api_hash_for_dict(data)

    assert "struct point_t field 0 view.nullable must be boolean" in validate_api_data(
        data
    )
