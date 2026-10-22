# plugins/math/commands.py
"""
Command actions and definitions supported by the Math Plugin.
"""

from typing import Any, Dict, List, Optional, Union
from core.permissions import PermissionLevel, PluginCapability
from plugins.manifest import PluginAction, PluginParameter
from .calculator import MathEngine
from .models import MathResult

ACTIONS = [
    PluginAction(
        name="calculate",
        description="Calculates arithmetic or scientific mathematical expression",
        keywords=["calculate", "hisaab", "jod", "ghatao", "guna", "bhaag", "evaluate", "math"],
        parameters=[
            PluginParameter(name="expression", type="string", description="Mathematical expression (e.g. 25 + 35, 125*8)", required=True),
            PluginParameter(name="step_by_step", type="boolean", description="Whether to include step-by-step breakdown", required=False, default=False)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="percentage",
        description="Calculates percentage operations (of, add, discount/minus)",
        keywords=["percentage", "percent", "pratishat", "discount", "tax"],
        parameters=[
            PluginParameter(name="base", type="number", description="Base number", required=True),
            PluginParameter(name="percent", type="number", description="Percentage value", required=True),
            PluginParameter(name="action", type="string", description="Action (of, add, discount, minus)", required=False, default="of"),
            PluginParameter(name="step_by_step", type="boolean", description="Whether to include step-by-step breakdown", required=False, default=False)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="power_root",
        description="Calculates squares, cubes, powers, square roots, and cube roots",
        keywords=["square", "cube", "root", "vargmool", "square root", "cube root", "power"],
        parameters=[
            PluginParameter(name="base", type="number", description="Base number", required=True),
            PluginParameter(name="operation", type="string", description="Operation (square, cube, sqrt, cbrt, power)", required=False, default="square"),
            PluginParameter(name="exponent", type="number", description="Exponent for power operation", required=False, default=2),
            PluginParameter(name="step_by_step", type="boolean", description="Whether to include step-by-step breakdown", required=False, default=False)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="solve_equation",
        description="Solves linear and quadratic algebraic equations",
        keywords=["solve equation", "equation", "samikaran", "algebra", "solve for x"],
        parameters=[
            PluginParameter(name="equation", type="string", description="Algebraic equation (e.g. 2x + 10 = 30)", required=True),
            PluginParameter(name="step_by_step", type="boolean", description="Whether to include step-by-step breakdown", required=False, default=False)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="statistics",
        description="Calculates statistical summary (mean, median, mode, variance, std dev)",
        keywords=["mean", "median", "mode", "average", "ausat", "statistics", "variance", "std dev"],
        parameters=[
            PluginParameter(name="numbers", type="list", description="List of numerical values", required=True),
            PluginParameter(name="metric", type="string", description="Specific metric or all", required=False, default="all")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="financial",
        description="Calculates simple and compound interest",
        keywords=["interest", "byaj", "simple interest", "compound interest", "loan interest"],
        parameters=[
            PluginParameter(name="principal", type="number", description="Principal amount", required=True),
            PluginParameter(name="rate", type="number", description="Annual interest rate percentage", required=True),
            PluginParameter(name="time_period", type="number", description="Time period in years", required=True),
            PluginParameter(name="mode", type="string", description="Mode (si, ci)", required=False, default="si"),
            PluginParameter(name="step_by_step", type="boolean", description="Whether to include step-by-step breakdown", required=False, default=False)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="unit_conversion",
        description="Converts measurements between metric and imperial units (length, mass, temp, speed, volume)",
        keywords=["convert unit", "celsius to fahrenheit", "kg to lbs", "km to miles"],
        parameters=[
            PluginParameter(name="value", type="number", description="Numeric value to convert", required=True),
            PluginParameter(name="from_unit", type="string", description="Source unit", required=True),
            PluginParameter(name="to_unit", type="string", description="Target unit", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="matrix_operations",
        description="Performs matrix algebra (addition, subtraction, multiplication, transpose, determinant)",
        keywords=["matrix math", "matrix multiply", "determinant", "transpose matrix"],
        parameters=[
            PluginParameter(name="matrix_a", type="list", description="Primary 2D matrix (list of lists)", required=True),
            PluginParameter(name="operation", type="string", description="Operation: add, subtract, multiply, transpose, determinant", required=True),
            PluginParameter(name="matrix_b", type="list", description="Secondary 2D matrix (optional)", required=False, default=[])
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="trigonometry",
        description="Evaluates trigonometric and hyperbolic functions (sin, cos, tan, asin, acos, atan)",
        keywords=["trigonometry", "sin", "cos", "tan", "trig"],
        parameters=[
            PluginParameter(name="function", type="string", description="Function: sin, cos, tan, asin, acos, atan, sinh, cosh, tanh", required=True),
            PluginParameter(name="value", type="number", description="Input value", required=True),
            PluginParameter(name="unit", type="string", description="Angle unit: degrees or radians", required=False, default="degrees")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="gcd_lcm",
        description="Calculates the Greatest Common Divisor (GCD) and Least Common Multiple (LCM)",
        keywords=["gcd", "lcm", "hcf", "greatest common divisor", "least common multiple"],
        parameters=[
            PluginParameter(name="numbers", type="list", description="List of integers", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="prime_factorization",
        description="Determines if a number is prime and computes its prime factors",
        keywords=["prime factors", "is prime", "prime factorization", "factors of"],
        parameters=[
            PluginParameter(name="number", type="integer", description="Integer to factorize", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="combinatorics",
        description="Calculates factorials (n!), permutations P(n,r), and combinations C(n,r)",
        keywords=["factorial", "permutation", "combination", "npr", "ncr"],
        parameters=[
            PluginParameter(name="n", type="integer", description="Total items (n)", required=True),
            PluginParameter(name="r", type="integer", description="Chosen items (r)", required=False, default=0),
            PluginParameter(name="operation", type="string", description="Operation: factorial, permutation, combination", required=False, default="combination")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="base_conversion",
        description="Converts integers between binary (base 2), octal (base 8), decimal (base 10), and hex (base 16)",
        keywords=["base conversion", "hex to decimal", "binary to hex", "decimal to binary"],
        parameters=[
            PluginParameter(name="value", type="string", description="Value string or number", required=True),
            PluginParameter(name="from_base", type="integer", description="Source base (2, 8, 10, 16)", required=False, default=10),
            PluginParameter(name="to_base", type="integer", description="Target base (2, 8, 10, 16)", required=False, default=16)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="tax_breakdown",
        description="Calculates net amount, sales tax/GST, discount, and gross total",
        keywords=["gst calculation", "tax breakdown", "vat calculator", "discount and tax"],
        parameters=[
            PluginParameter(name="amount", type="number", description="Base amount", required=True),
            PluginParameter(name="tax_rate", type="number", description="Tax rate percentage (e.g. 18 for 18%)", required=True),
            PluginParameter(name="discount_percent", type="number", description="Discount percentage", required=False, default=0.0)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="loan_emi",
        description="Calculates monthly loan EMI, total interest, and full repayment schedule",
        keywords=["emi calculator", "loan emi", "home loan emi", "car loan emi"],
        parameters=[
            PluginParameter(name="principal", type="number", description="Loan principal amount", required=True),
            PluginParameter(name="annual_rate", type="number", description="Annual interest rate percentage", required=True),
            PluginParameter(name="tenure_months", type="integer", description="Loan tenure in months", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="vector_math",
        description="Calculates vector dot product, cross product, magnitude, and angle",
        keywords=["vector math", "dot product", "cross product", "vector magnitude"],
        parameters=[
            PluginParameter(name="vector_a", type="list", description="First vector [x, y, z]", required=True),
            PluginParameter(name="vector_b", type="list", description="Second vector [x, y, z]", required=False, default=[]),
            PluginParameter(name="operation", type="string", description="Operation: dot, cross, magnitude, angle", required=False, default="dot")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    )
]


class MathCommands:
    """Executable command handlers for the Math subsystem."""

    def __init__(self, engine: Optional[MathEngine] = None):
        self.engine = engine or MathEngine()

    def calculate(self, expression: str, step_by_step: bool = False) -> Dict[str, Any]:
        """Calculates arithmetic or scientific mathematical expression."""
        res: MathResult = self.engine.calculate(expression, explain=step_by_step)
        return res.to_dict()

    def percentage(
        self,
        base: float,
        percent: float,
        action: str = "of",
        step_by_step: bool = False
    ) -> Dict[str, Any]:
        """Calculates percentages (of, add tax, discount minus)."""
        res: MathResult = self.engine.calculate_percentage(
            base_value=float(base),
            percentage=float(percent),
            action=action,
            explain=step_by_step
        )
        return res.to_dict()

    def power_root(
        self,
        base: float,
        operation: str = "square",
        exponent: Optional[float] = None,
        step_by_step: bool = False
    ) -> Dict[str, Any]:
        """Calculates squares, cubes, powers, square roots, cube roots."""
        res: MathResult = self.engine.calculate_power_root(
            base_value=float(base),
            operation=operation,
            exponent=float(exponent) if exponent is not None else None,
            explain=step_by_step
        )
        return res.to_dict()

    def solve_equation(self, equation: str, step_by_step: bool = False) -> Dict[str, Any]:
        """Solves algebraic linear and quadratic equations."""
        res: MathResult = self.engine.solve_equation(equation, explain=step_by_step)
        return res.to_dict()

    def statistics(self, numbers: List[float], metric: str = "all") -> Dict[str, Any]:
        """Computes statistical metrics (mean, median, mode, variance, std dev)."""
        res: MathResult = self.engine.calculate_statistics(numbers, metric=metric)
        return res.to_dict()

    def financial(
        self,
        principal: float,
        rate: float,
        time_period: float,
        mode: str = "si",
        step_by_step: bool = False
    ) -> Dict[str, Any]:
        """Calculates Simple / Compound Interest."""
        res: MathResult = self.engine.calculate_financial(
            principal=float(principal),
            rate=float(rate),
            time_period=float(time_period),
            mode=mode,
            explain=step_by_step
        )
        return res.to_dict()
