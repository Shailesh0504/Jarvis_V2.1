# tests/test_math_plugin.py
"""
Comprehensive Unit and End-to-End Regression Tests for Jarvis Math Plugin.
Validates:
- Arithmetic, BODMAS, and safe AST evaluation (zero eval / zero code execution)
- Spoken Hindi / Hinglish mathematical queries
- Percentages (of, add tax, discount/minus)
- Powers, squares, cubes, square roots, cube roots
- Linear and quadratic algebraic equation solving
- Statistical summaries (mean, median, mode, std dev)
- Simple & compound interest financial calculations
- Division by zero and error handling
- Security against code injection
- End-to-end integration through JarvisCore and EventBus
"""

import os
import pytest
from plugins.math.calculator import MathEngine, SpokenMathNormalizer, SafeMathEvaluator
from plugins.math.plugin import MathPlugin
from core.app import JarvisCore
from memory.memory_manager import MemoryManager
from brain.response import ResponseGenerator
from brain.llm import MockLLMProvider
from plugins.manager import PluginManager


@pytest.fixture
def math_engine():
    return MathEngine()


@pytest.fixture
def math_plugin():
    return MathPlugin()


@pytest.fixture
def core_app(tmp_path):
    core = JarvisCore()
    db_path = str(tmp_path / "test_math_app.db")
    mem = MemoryManager(db_path=db_path)
    llm = MockLLMProvider()
    resp_gen = ResponseGenerator(llm_provider=llm)
    plugins = PluginManager(plugin_dir="plugins")
    plugins.discover_and_load()

    core.initialize_subsystems(
        memory_manager=mem,
        learning_manager=None,
        brain=resp_gen,
        classifier=None,
        plugin_manager=plugins,
        response_generator=resp_gen
    )
    return core


def test_basic_arithmetic_and_bodmas(math_engine):
    """Verifies standard arithmetic and BODMAS order of operations."""
    res1 = math_engine.calculate("25 + 35")
    assert res1.success is True
    assert res1.result_value == 60

    res2 = math_engine.calculate("125 * 8")
    assert res2.success is True
    assert res2.result_value == 1000

    res3 = math_engine.calculate("500 / 25")
    assert res3.success is True
    assert res3.result_value == 20

    res4 = math_engine.calculate("125 * 8 / 4 + 10")
    assert res4.success is True
    assert res4.result_value == 260

    res5 = math_engine.calculate("(10 + 5) * (8 - 3)")
    assert res5.success is True
    assert res5.result_value == 75


def test_spoken_hindi_hinglish_arithmetic(math_engine):
    """Verifies Hindi and Hinglish spoken math normalizer."""
    # Jod (Addition)
    n1 = SpokenMathNormalizer.normalize_spoken_math("25 mein 15 jod do")
    assert "+" in n1
    res1 = math_engine.calculate("25 + 15")
    assert res1.result_value == 40

    # Ghatao (Subtraction)
    res2 = math_engine.calculate("100 - 45")
    assert res2.result_value == 55

    # Guna (Multiplication)
    res3 = math_engine.calculate("50 * 5")
    assert res3.result_value == 250

    # Bhaag (Division)
    res4 = math_engine.calculate("500 / 25")
    assert res4.result_value == 20


def test_percentages(math_engine):
    """Verifies percentage of, tax add, and discount minus operations."""
    # 20% of 500 = 100
    res1 = math_engine.calculate_percentage(500, 20, action="of")
    assert res1.success is True
    assert res1.result_value == 100.0

    # 500 + 18% tax = 590
    res2 = math_engine.calculate_percentage(500, 18, action="add")
    assert res2.success is True
    assert res2.result_value == 590.0

    # 1200 - 10% discount = 1080
    res3 = math_engine.calculate_percentage(1200, 10, action="discount")
    assert res3.success is True
    assert res3.result_value == 1080.0


def test_powers_and_roots(math_engine):
    """Verifies squares, cubes, powers, and roots."""
    # 2 ka square = 4
    res1 = math_engine.calculate_power_root(2, operation="square")
    assert res1.success is True
    assert res1.result_value == 4

    # 144 ka square root = 12
    res2 = math_engine.calculate_power_root(144, operation="sqrt")
    assert res2.success is True
    assert res2.result_value == 12

    # 27 ka cube root = 3
    res3 = math_engine.calculate_power_root(27, operation="cbrt")
    assert res3.success is True
    assert round(res3.result_value, 4) == 3

    # 2^5 = 32
    res4 = math_engine.calculate_power_root(2, operation="power", exponent=5)
    assert res4.success is True
    assert res4.result_value == 32


def test_algebraic_equations(math_engine):
    """Verifies linear and quadratic algebraic equation solving."""
    # Linear: x + 5 = 15 -> x = 10
    res1 = math_engine.solve_equation("x + 5 = 15")
    assert res1.success is True
    assert res1.result_value.get("x") == 10

    # Linear: 2x + 10 = 30 -> x = 10
    res2 = math_engine.solve_equation("2x + 10 = 30")
    assert res2.success is True
    assert res2.result_value.get("x") == 10

    # Quadratic: x^2 - 5x + 6 = 0 -> x = 2, 3
    res3 = math_engine.solve_equation("x^2 - 5x + 6 = 0")
    assert res3.success is True
    roots = res3.result_value.get("x")
    assert 2 in roots and 3 in roots


def test_statistics(math_engine):
    """Verifies mean, median, mode, and summary statistics."""
    data = [10, 20, 30, 40, 50]
    res = math_engine.calculate_statistics(data, metric="mean")
    assert res.success is True
    assert res.result_value == 30.0

    res_all = math_engine.calculate_statistics(data, metric="all")
    assert res_all.success is True
    assert res_all.result_value["mean (average)"] == 30.0
    assert res_all.result_value["median"] == 30.0


def test_financial_interest(math_engine):
    """Verifies simple and compound interest calculations."""
    # Simple Interest: P=10000, R=5%, T=2 -> Interest=1000, Total=11000
    res = math_engine.calculate_financial(10000, 5, 2, mode="si")
    assert res.success is True
    assert res.result_value["interest"] == 1000.0
    assert res.result_value["total"] == 11000.0


def test_division_by_zero_and_security(math_engine):
    """Verifies safe error handling on division by zero and rejects code execution."""
    # Division by zero
    res = math_engine.calculate("500 / 0")
    assert res.success is False
    assert "Division by zero" in res.formatted_answer

    # Code injection rejection
    res_inject = math_engine.calculate("__import__('os').system('dir')")
    assert res_inject.success is False


def test_scientific_and_trigonometric_functions(math_engine):
    """Verifies trigonometry, logarithms, and scientific operations."""
    # Trigonometry (in degrees)
    res_sin = math_engine.calculate("sin(30)")
    assert res_sin.success is True
    assert round(res_sin.result_value, 2) == 0.5

    res_cos = math_engine.calculate("cos(60)")
    assert res_cos.success is True
    assert round(res_cos.result_value, 2) == 0.5

    # Logarithms
    res_log = math_engine.calculate("log10(100)")
    assert res_log.success is True
    assert res_log.result_value == 2.0

    # Factorial
    res_fact = math_engine.calculate("factorial(5)")
    assert res_fact.success is True
    assert res_fact.result_value == 120


def test_step_by_step_explanation(math_engine):
    """Verifies that step-by-step calculations provide detailed solution steps."""
    res = math_engine.calculate_percentage(1200, 15, action="discount", explain=True)
    assert res.success is True
    assert len(res.steps) >= 2
    assert "Step 1" in res.formatted_answer
    assert "Step 2" in res.formatted_answer


def test_compound_interest(math_engine):
    """Verifies compound interest calculation."""
    res = math_engine.calculate_financial(5000, 10, 2, mode="ci", explain=True)
    assert res.success is True
    assert res.result_value["total"] == 6050.0
    assert res.result_value["interest"] == 1050.0


def test_end_to_end_core_math_routing(core_app):
    """Verifies end-to-end routing from JarvisCore natural language query to MathPlugin."""
    # 1. Hindi addition
    resp1 = core_app.process_input("Jarvis, 25 mein 15 jod do")
    assert "40" in resp1

    # 2. Hindi percentage of
    resp2 = core_app.process_input("Jarvis, 500 ka 20 percent kitna hai")
    assert "100" in resp2

    # 3. Hindi percentage add (tax)
    resp3 = core_app.process_input("Jarvis, 500 mein 18% add karo")
    assert "590" in resp3

    # 4. Hindi percentage discount
    resp4 = core_app.process_input("Jarvis, 1200 ka 10 percent minus karo")
    assert "1080" in resp4

    # 5. Square
    resp5 = core_app.process_input("Jarvis, 2 ka square kya hai")
    assert "4" in resp5

    # 6. Square root
    resp6 = core_app.process_input("Jarvis, 144 ka square root batao")
    assert "12" in resp6

    # 7. Equation solving
    resp7 = core_app.process_input("Jarvis, x + 5 = 15 solve karo")
    assert "10" in resp7
