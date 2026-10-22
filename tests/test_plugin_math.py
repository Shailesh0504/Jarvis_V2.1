# tests/test_plugin_math.py
"""Tests for MathPlugin covering original and newly added actions."""

import pytest
from plugins.math.plugin import MathPlugin


@pytest.fixture
def plugin():
    p = MathPlugin()
    p.initialize()
    return p


def test_math_manifest(plugin):
    manifest = plugin.get_manifest()
    assert manifest.name == "math"
    action_names = {a.name for a in manifest.actions}
    expected = {
        "calculate",
        "percentage",
        "power_root",
        "solve_equation",
        "statistics",
        "financial",
        "unit_conversion",
        "matrix_operations",
        "trigonometry",
        "gcd_lcm",
        "prime_factorization",
        "combinatorics",
        "base_conversion",
        "tax_breakdown",
        "loan_emi",
        "vector_math"
    }
    assert expected.issubset(action_names)


def test_math_original_features(plugin):
    # Calculate expression
    res_calc = plugin.execute("calculate", {"expression": "25 * 4 + 10"})
    assert res_calc.success is True
    assert res_calc.data["result_value"] == 110

    # Percentage
    res_pct = plugin.execute("percentage", {"base": 500, "percent": 15, "action": "of"})
    assert res_pct.success is True
    assert res_pct.data["result_value"] == 75

    # Power root
    res_sqrt = plugin.execute("power_root", {"base": 144, "operation": "sqrt"})
    assert res_sqrt.success is True
    assert res_sqrt.data["result_value"] == 12

    # Statistics
    res_stats = plugin.execute("statistics", {"numbers": [10, 20, 30, 40, 50], "metric": "mean"})
    assert res_stats.success is True
    assert res_stats.data["result_value"] == 30.0


def test_math_unit_conversion_and_trig(plugin):
    # Unit conversion length
    res_km = plugin.execute("unit_conversion", {"value": 5, "from_unit": "km", "to_unit": "m"})
    assert res_km.success is True
    assert res_km.data["result"] == 5000

    # Unit conversion temp
    res_temp = plugin.execute("unit_conversion", {"value": 100, "from_unit": "c", "to_unit": "f"})
    assert res_temp.success is True
    assert res_temp.data["result"] == 212

    # Trigonometry
    res_sin = plugin.execute("trigonometry", {"function": "sin", "value": 90, "unit": "degrees"})
    assert res_sin.success is True
    assert round(res_sin.data["result"], 1) == 1.0


def test_math_matrix_and_vector(plugin):
    # Matrix multiplication
    mat_a = [[1, 2], [3, 4]]
    mat_b = [[2, 0], [1, 2]]
    res_mat = plugin.execute("matrix_operations", {"matrix_a": mat_a, "matrix_b": mat_b, "operation": "multiply"})
    assert res_mat.success is True
    assert res_mat.data["result"] == [[4, 4], [10, 8]]

    # Matrix determinant
    res_det = plugin.execute("matrix_operations", {"matrix_a": mat_a, "operation": "determinant"})
    assert res_det.success is True
    assert res_det.data["result"] == -2

    # Vector dot product
    res_dot = plugin.execute("vector_math", {"vector_a": [1, 2, 3], "vector_b": [4, 5, 6], "operation": "dot"})
    assert res_dot.success is True
    assert res_dot.data["result"] == 32

    # Vector magnitude
    res_mag = plugin.execute("vector_math", {"vector_a": [3, 4], "operation": "magnitude"})
    assert res_mag.success is True
    assert res_mag.data["result"] == 5.0


def test_math_number_theory_and_combinatorics(plugin):
    # GCD & LCM
    res_gcd = plugin.execute("gcd_lcm", {"numbers": [24, 36, 60]})
    assert res_gcd.success is True
    assert res_gcd.data["gcd"] == 12
    assert res_gcd.data["lcm"] == 360

    # Prime factorization
    res_prime = plugin.execute("prime_factorization", {"number": 360})
    assert res_prime.success is True
    assert res_prime.data["is_prime"] is False
    assert res_prime.data["factors"] == {2: 3, 3: 2, 5: 1}

    # Combinatorics
    res_comb = plugin.execute("combinatorics", {"n": 5, "r": 2, "operation": "combination"})
    assert res_comb.success is True
    assert res_comb.data["result"] == 10

    res_perm = plugin.execute("combinatorics", {"n": 5, "r": 2, "operation": "permutation"})
    assert res_perm.success is True
    assert res_perm.data["result"] == 20


def test_math_finance_and_tax_and_bases(plugin):
    # Base conversion
    res_base = plugin.execute("base_conversion", {"value": "255", "from_base": 10, "to_base": 16})
    assert res_base.success is True
    assert res_base.data["result"] == "FF"

    # Tax breakdown
    res_tax = plugin.execute("tax_breakdown", {"amount": 1000, "tax_rate": 18, "discount_percent": 10})
    assert res_tax.success is True
    assert res_tax.data["discount_amount"] == 100.0
    assert res_tax.data["net_taxable_amount"] == 900.0
    assert res_tax.data["tax_amount"] == 162.0
    assert res_tax.data["gross_total"] == 1062.0

    # Loan EMI
    res_emi = plugin.execute("loan_emi", {"principal": 100000, "annual_rate": 12, "tenure_months": 12})
    assert res_emi.success is True
    assert res_emi.data["monthly_emi"] > 8800
    assert res_emi.data["total_payment"] > 100000
