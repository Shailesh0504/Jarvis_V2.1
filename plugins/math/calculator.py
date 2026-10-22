# plugins/math/calculator.py
"""
Deterministic Local Mathematical Computation Engine and Spoken Math Normalizer.
Safe, zero-API, zero-eval AST evaluation with support for Hindi/Hinglish/English speech.
"""

import ast
from decimal import Decimal, getcontext
import math
import operator
import re
import statistics
from typing import Any, Dict, List, Optional, Tuple, Union

from .models import MathOperationType, MathResult

getcontext().prec = 28


class SpokenMathNormalizer:
    """Normalizes natural Hindi, Hinglish, and English spoken math into formal mathematical notation."""

    NUMBER_WORDS = {
        "shunya": "0", "zero": "0", "ek": "1", "one": "1", "do": "2", "two": "2",
        "teen": "3", "three": "3", "chaar": "4", "char": "4", "four": "4",
        "paanch": "5", "panch": "5", "five": "5", "chhah": "6", "chhe": "6", "six": "6",
        "saat": "7", "sat": "7", "seven": "7", "aath": "8", "ath": "8", "eight": "8",
        "nau": "9", "no": "9", "nine": "9", "das": "10", "ten": "10",
        "sau": "100", "hundred": "100", "hazaar": "1000", "thousand": "1000",
        "lakh": "100000", "crore": "10000000"
    }

    OPERATOR_PHRASES = [
        (r'\b(?:divided\s+by|divide\s+by|bhaag\s+karo|bhaag\s+do|bhaag|banta)\b', '/'),
        (r'\b(?:multiplied\s+by|multiply\s+by|guna\s+karo|guna\s+kar\s+do|guna|into|times)\b', '*'),
        (r'\b(?:plus|add\s+karo|jod\s+do|jodo|jod|jama)\b', '+'),
        (r'\b(?:minus|subtract|ghatao|ghata\s+do|kam\s+karo)\b', '-'),
        (r'\b(?:equals|equal\s+to|barabar\s+hai|barabar)\b', '='),
        (r'\b(?:point|dashamlav)\b', '.'),
        (r'\b(?:percent|percentage|pratishat|faisad)\b', '%'),
        (r'\b(?:square\s+root\s+of|vargmool)\b', 'sqrt'),
        (r'\b(?:cube\s+root\s+of|ghanmool)\b', 'cbrt'),
        (r'\b(?:to\s+the\s+power\s+of|ki\s+power|power)\b', '^'),
    ]

    @classmethod
    def normalize_spoken_math(cls, text: str) -> str:
        if not text or not text.strip():
            return ""

        s = text.strip().lower()

        # Remove polite/filler prefixes
        s = re.sub(r'^(?:jarvis|please|batao|kya\s+hoga|kya\s+hai|calculate|solve|iska\s+answer|answer\s+batao|find|compute|what\s+is|what\'s)\s*[,:]?\s*', '', s)

        # Structural Hindi calculation patterns (e.g. "25 mein 15 jod do" -> "25 + 15")
        s = re.sub(r'(\d+(?:\.\d+)?)\s*(?:mein|me)\s*(\d+(?:\.\d+)?)\s*(?:jod\s+do|jodo|jod|jama|add\s+karo|plus)', r'\1 + \2', s)
        s = re.sub(r'(\d+(?:\.\d+)?)\s*(?:mein\s+se|se)\s*(\d+(?:\.\d+)?)\s*(?:ghatao|ghata\s+do|minus|kam\s+karo)', r'\1 - \2', s)
        s = re.sub(r'(\d+(?:\.\d+)?)\s*(?:ka|ko)\s*(\d+(?:\.\d+)?)\s*(?:se\s+)?(?:guna\s+karo|guna|times|into|multiply)', r'\1 * \2', s)
        s = re.sub(r'(\d+(?:\.\d+)?)\s*(?:ko)\s*(\d+(?:\.\d+)?)\s*(?:se\s+)?(?:bhaag\s+do|bhaag|divide)', r'\1 / \2', s)

        # Replace phrase operators
        for pat, repl in cls.OPERATOR_PHRASES:
            s = re.sub(pat, f" {repl} ", s, flags=re.IGNORECASE)

        # Remove polite/filler suffixes (incl. common STT variants kitana/kitne/kithna; optional trailing ?)
        s = re.sub(r'\s+(?:kit(?:na|ne|ana|ane)\s+(?:hota\s+hai|hoga|hai)|kya\s+(?:hota\s+hai|hoga|hai)|batao|bataiye|karo|kar\s+do|hoga|nikalo|solve\s+karo|step\s+by\s+step|please)[?!\s]*$', '', s)

        # Remove trailing equals, question marks, and query suffixes like =?, = ?, ?
        s = re.sub(r'[=\?\s]+$', '', s).strip()

        # Clean spaces
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    # Single authoritative math-query gate for the whole assistant.
    # Used by InputQuality, SpeechConfidence, FastPath, ConversationalIntent
    # so short expressions like "2+2=?" are never treated as noise.
    _MATH_CORE_RE = re.compile(
        r'\d+(?:\.\d+)?\s*(?:[\+\-\*\/\^%x×÷]|times|plus|minus|into|divided\s+by|divide\s+by|multiplied\s+by|guna|bhaag|jod|ghatao)\s*\d+',
        re.IGNORECASE,
    )
    _MATH_FUNC_RE = re.compile(
        r'\b(?:sqrt|cbrt|sin|cos|tan|log|ln|exp|factorial|square|cube|power|root|vargmool|ghanmool|varg|ghan|square\s+root|cube\s+root)\b',
        re.IGNORECASE,
    )
    _MATH_HINDI_OP_RE = re.compile(
        r'\b(?:jod|jodo|ghatao|guna|bhaag|plus|minus|times|into|divide|multiply|hisaab|ganit|square|cube|power|root|varg|ghan)\b',
        re.IGNORECASE,
    )

    @classmethod
    def is_math_query(cls, text: str) -> bool:
        """True for deterministic math requests (digits+operator or math functions)."""
        if not text or not text.strip():
            return False
        s = text.strip().lower()
        # Must contain at least one digit to avoid hijacking chitchat
        if not re.search(r'\d', s):
            # Allow pure function words with numbers only; else not math
            return False
        if cls._MATH_CORE_RE.search(s):
            return True
        # Hindi structural: "25 mein 15 jod do", "10 ka 20% ", "2+2 kitna hota hai"
        norm = cls.normalize_spoken_math(text)
        if norm and re.search(r'\d', norm) and re.search(r'[\+\-\*\/\^%]', norm):
            return True
        if cls._MATH_FUNC_RE.search(s) and re.search(r'\d', s):
            return True
        if cls._MATH_HINDI_OP_RE.search(s) and re.search(r'\d', s):
            # e.g. "25 mein 15 jod do", "2+2 kitana hota hai" (operator present via + or word)
            return True
        return False


class SafeMathEvaluator(ast.NodeVisitor):
    """AST-based safe math expression evaluator supporting arithmetic, powers, and math functions."""

    ALLOWED_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    ALLOWED_FUNCTIONS = {
        "sqrt": math.sqrt,
        "cbrt": lambda x: math.pow(x, 1/3) if x >= 0 else -math.pow(-x, 1/3),
        "abs": abs,
        "round": round,
        "sin": lambda x: math.sin(math.radians(x)),
        "cos": lambda x: math.cos(math.radians(x)),
        "tan": lambda x: math.tan(math.radians(x)),
        "asin": lambda x: math.degrees(math.asin(x)),
        "acos": lambda x: math.degrees(math.acos(x)),
        "atan": lambda x: math.degrees(math.atan(x)),
        "log": math.log,
        "log10": math.log10,
        "log2": math.log2,
        "ln": math.log,
        "exp": math.exp,
        "factorial": math.factorial,
        "floor": math.floor,
        "ceil": math.ceil,
        "radians": math.radians,
        "degrees": math.degrees,
    }

    ALLOWED_CONSTANTS = {
        "pi": math.pi,
        "e": math.e,
        "tau": math.tau,
        "inf": math.inf
    }

    def evaluate(self, expr_str: str) -> Tuple[Union[int, float], List[str]]:
        # Normalize ^ to **
        clean_expr = expr_str.replace("^", "**").strip()

        # Parse AST
        try:
            node = ast.parse(clean_expr, mode='eval')
        except SyntaxError as e:
            raise ValueError(f"Invalid mathematical syntax: {expr_str}")

        steps = []
        result = self.visit(node.body)
        return result, steps

    def visit_BinOp(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)
        op_type = type(node.op)
        if op_type not in self.ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")

        op_func = self.ALLOWED_OPERATORS[op_type]
        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Division by zero is undefined.")

        return op_func(left, right)

    def visit_UnaryOp(self, node):
        operand = self.visit(node.operand)
        op_type = type(node.op)
        if op_type not in self.ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        return self.ALLOWED_OPERATORS[op_type](operand)

    def visit_Constant(self, node):
        if isinstance(node.value, (int, float, complex)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")

    def visit_Num(self, node): # Python <3.8 compatibility
        return node.n

    def visit_Name(self, node):
        name = node.id.lower()
        if name in self.ALLOWED_CONSTANTS:
            return self.ALLOWED_CONSTANTS[name]
        raise ValueError(f"Undefined mathematical variable or constant: '{node.id}'")

    def visit_Call(self, node):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Unsupported function call")
        func_name = node.func.id.lower()
        if func_name not in self.ALLOWED_FUNCTIONS:
            raise ValueError(f"Unsupported function: '{func_name}()'")

        args = [self.visit(arg) for arg in node.args]
        func = self.ALLOWED_FUNCTIONS[func_name]
        try:
            return func(*args)
        except Exception as e:
            raise ValueError(f"Error calculating {func_name}: {e}")

    def generic_visit(self, node):
        raise ValueError(f"Disallowed AST element for security: {type(node).__name__}")


class MathEngine:
    """Comprehensive Local Math Solver Engine."""

    def __init__(self):
        self.evaluator = SafeMathEvaluator()

    def calculate(self, expression_str: str, explain: bool = False) -> MathResult:
        """Evaluates arbitrary arithmetic and scientific expressions safely."""
        norm = SpokenMathNormalizer.normalize_spoken_math(expression_str)
        if not norm:
            return MathResult(
                success=False,
                operation=MathOperationType.ARITHMETIC,
                expression=expression_str,
                result_value=None,
                formatted_answer="Kripya koi valid mathematical expression dein.",
                error="empty_expression"
            )

        steps = []
        if explain:
            steps.append(f"Given Expression: {norm}")

        try:
            val, eval_steps = self.evaluator.evaluate(norm)
            steps.extend(eval_steps)

            # Clean integer vs float presentation
            if isinstance(val, float) and val.is_integer():
                display_val = int(val)
            elif isinstance(val, float):
                display_val = round(val, 8)
            else:
                display_val = val

            if explain:
                steps.append(f"Final Evaluated Value: {display_val}")
                formatted = f"{norm} = {display_val}\n\nSteps:\n" + "\n".join(f"• {s}" for s in steps)
            else:
                formatted = f"{norm} = {display_val}"

            return MathResult(
                success=True,
                operation=MathOperationType.ARITHMETIC,
                expression=norm,
                result_value=display_val,
                formatted_answer=formatted,
                steps=steps
            )
        except ZeroDivisionError as zde:
            return MathResult(
                success=False,
                operation=MathOperationType.ARITHMETIC,
                expression=norm,
                result_value=None,
                formatted_answer="Error: 0 se divide nahi kiya ja sakta (Division by zero is undefined).",
                error=str(zde)
            )
        except Exception as e:
            return MathResult(
                success=False,
                operation=MathOperationType.ARITHMETIC,
                expression=norm,
                result_value=None,
                formatted_answer=f"Calculation error: {e}",
                error=str(e)
            )

    def calculate_percentage(
        self,
        base_value: float,
        percentage: float,
        action: str = "of",
        explain: bool = False
    ) -> MathResult:
        """
        Handles percentage calculations:
        - "of": 20% of 500 = 100
        - "add": 500 + 18% tax = 590
        - "discount" / "minus": 1200 - 15% = 1020
        """
        steps = []
        pct_amount = (base_value * percentage) / 100.0
        steps.append(f"Step 1: Calculate {percentage}% of {base_value} = ({base_value} × {percentage}) / 100 = {pct_amount}")

        if action in ("add", "plus", "tax", "increment"):
            final_val = base_value + pct_amount
            steps.append(f"Step 2: Add to base value = {base_value} + {pct_amount} = {final_val}")
            ans_str = f"{base_value} mein {percentage}% add karne par: {final_val} ({percentage}% = {pct_amount})"
        elif action in ("discount", "minus", "subtract", "decrement"):
            final_val = base_value - pct_amount
            steps.append(f"Step 2: Deduct from base value = {base_value} - {pct_amount} = {final_val}")
            ans_str = f"{base_value} mein se {percentage}% discount/minus karne par: {final_val} (Discount = {pct_amount})"
        else:
            final_val = pct_amount
            ans_str = f"{base_value} ka {percentage}% = {final_val}"

        if explain:
            formatted = ans_str + "\n\nSteps:\n" + "\n".join(f"• {s}" for s in steps)
        else:
            formatted = ans_str

        return MathResult(
            success=True,
            operation=MathOperationType.PERCENTAGE,
            expression=f"{percentage}% {action} {base_value}",
            result_value=final_val,
            formatted_answer=formatted,
            steps=steps
        )

    def calculate_power_root(
        self,
        base_value: float,
        operation: str = "square",
        exponent: Optional[float] = None,
        explain: bool = False
    ) -> MathResult:
        """Calculates Square, Cube, Power, Square Root, Cube Root."""
        steps = []
        op_lower = operation.lower().strip()

        if op_lower in ("square", "varg"):
            res = base_value ** 2
            steps.append(f"{base_value} का square (varg) = {base_value} × {base_value} = {res}")
            formatted = f"{base_value}² = {res}"
        elif op_lower in ("cube", "ghan"):
            res = base_value ** 3
            steps.append(f"{base_value} का cube = {base_value} × {base_value} × {base_value} = {res}")
            formatted = f"{base_value}³ = {res}"
        elif op_lower in ("sqrt", "square_root", "vargmool", "root"):
            if base_value < 0:
                return MathResult(
                    success=False,
                    operation=MathOperationType.POWER_ROOT,
                    expression=f"sqrt({base_value})",
                    result_value=None,
                    formatted_answer="Negative number ka real square root nahi hota.",
                    error="negative_sqrt"
                )
            res = math.sqrt(base_value)
            steps.append(f"√{base_value} = {res}")
            formatted = f"√{base_value} = {res}"
        elif op_lower in ("cbrt", "cube_root", "ghanmool"):
            res = math.pow(base_value, 1/3) if base_value >= 0 else -math.pow(-base_value, 1/3)
            steps.append(f"³√{base_value} = {res}")
            formatted = f"³√{base_value} = {res}"
        elif exponent is not None:
            res = base_value ** exponent
            steps.append(f"{base_value}^{exponent} = {res}")
            formatted = f"{base_value}^{exponent} = {res}"
        else:
            res = base_value ** 2
            formatted = f"{base_value}² = {res}"

        if isinstance(res, float) and res.is_integer():
            res = int(res)

        if explain and steps:
            formatted = formatted + "\n\nSteps:\n" + "\n".join(f"• {s}" for s in steps)

        return MathResult(
            success=True,
            operation=MathOperationType.POWER_ROOT,
            expression=f"{operation}({base_value})",
            result_value=res,
            formatted_answer=formatted,
            steps=steps
        )

    def solve_equation(self, eq_str: str, explain: bool = False) -> MathResult:
        """
        Solves linear and quadratic algebraic equations:
        - Linear: ax + b = c  (e.g. 'x + 5 = 15' -> x = 10, '2x + 10 = 30' -> x = 10)
        - Quadratic: ax^2 + bx + c = 0 (e.g. 'x^2 - 5x + 6 = 0' -> x = 2, 3)
        """
        steps = []
        raw = eq_str.strip().lower()

        # Clean words
        clean_eq = re.sub(r'^(?:solve|find\s+x|kya\s+hoga|equation)\s+', '', raw)
        clean_eq = re.sub(r'\s+(?:solve\s+karo|batao|nikalo)$', '', clean_eq)
        clean_eq = clean_eq.replace("equals", "=").replace("barabar", "=").replace("into", "*")
        clean_eq = clean_eq.replace(" ", "")

        steps.append(f"Equation: {clean_eq}")

        # 1. Linear Equation: ax + b = c or a*x + b = c
        m_linear = re.match(r'^([+-]?\d*\.?\d*)\*?([a-zA-Z])([+-]\d+\.?\d*)?=([+-]?\d+\.?\d*)$', clean_eq)
        if m_linear:
            a_str, var_name, b_str, c_str = m_linear.groups()
            a = float(a_str) if a_str and a_str not in ("+", "-") else (-1.0 if a_str == "-" else 1.0)
            b = float(b_str) if b_str else 0.0
            c = float(c_str) if c_str else 0.0

            if a == 0:
                return MathResult(
                    success=False,
                    operation=MathOperationType.EQUATION,
                    expression=clean_eq,
                    result_value=None,
                    formatted_answer="Invalid equation: Coefficient of variable is 0.",
                    error="zero_coefficient"
                )

            steps.append(f"Standard Linear Form: {a}{var_name} + ({b}) = {c}")
            steps.append(f"Subtract {b} from both sides: {a}{var_name} = {c - b}")
            steps.append(f"Divide by {a}: {var_name} = ({c - b}) / {a}")

            x_val = (c - b) / a
            if x_val.is_integer():
                x_val = int(x_val)

            steps.append(f"Solution: {var_name} = {x_val}")
            ans_str = f"{var_name} = {x_val}"

            if explain:
                formatted = f"Equation Solution:\n{ans_str}\n\nSteps:\n" + "\n".join(f"• {s}" for s in steps)
            else:
                formatted = f"Equation Solution: {ans_str}"

            return MathResult(
                success=True,
                operation=MathOperationType.EQUATION,
                expression=clean_eq,
                result_value={var_name: x_val},
                formatted_answer=formatted,
                steps=steps
            )

        # 2. Quadratic Equation: ax^2 + bx + c = 0
        m_quad = re.match(r'^([+-]?\d*\.?\d*)\*?([a-zA-Z])\^?2([+-]\d*\.?\d*)\*?\2?([+-]\d+\.?\d*)?=0$', clean_eq)
        if m_quad:
            a_str, var_name, b_str, c_str = m_quad.groups()
            a = float(a_str) if a_str and a_str not in ("+", "-") else (-1.0 if a_str == "-" else 1.0)
            b = float(b_str) if b_str and b_str not in ("+", "-") else (-1.0 if b_str == "-" else (1.0 if b_str == "+" else 0.0))
            c = float(c_str) if c_str else 0.0

            d = b**2 - 4*a*c
            steps.append(f"Quadratic Coefficients: a = {a}, b = {b}, c = {c}")
            steps.append(f"Discriminant D = b² - 4ac = ({b})² - 4({a})({c}) = {d}")

            if d < 0:
                steps.append("Since D < 0, roots are complex (no real roots).")
                r1 = complex(-b / (2*a), math.sqrt(-d) / (2*a))
                r2 = complex(-b / (2*a), -math.sqrt(-d) / (2*a))
                ans_str = f"{var_name}₁ = {r1}, {var_name}₂ = {r2} (Complex roots)"
                res_val = [r1, r2]
            elif d == 0:
                x = -b / (2*a)
                if x.is_integer(): x = int(x)
                steps.append(f"Since D = 0, equal real root: {var_name} = {-b} / (2×{a}) = {x}")
                ans_str = f"{var_name} = {x}"
                res_val = [x]
            else:
                x1 = (-b + math.sqrt(d)) / (2*a)
                x2 = (-b - math.sqrt(d)) / (2*a)
                if x1.is_integer(): x1 = int(x1)
                if x2.is_integer(): x2 = int(x2)
                steps.append(f"Roots: {var_name} = (-b ± √D) / 2a = ({-b} ± √{d}) / {2*a}")
                steps.append(f"{var_name}₁ = {x1}, {var_name}₂ = {x2}")
                ans_str = f"{var_name} = {x1}, {var_name} = {x2}"
                res_val = [x1, x2]

            if explain:
                formatted = f"Quadratic Solution:\n{ans_str}\n\nSteps:\n" + "\n".join(f"• {s}" for s in steps)
            else:
                formatted = f"Quadratic Solution: {ans_str}"

            return MathResult(
                success=True,
                operation=MathOperationType.EQUATION,
                expression=clean_eq,
                result_value={var_name: res_val},
                formatted_answer=formatted,
                steps=steps
            )

        # Fallback to general algebraic simplification
        return MathResult(
            success=False,
            operation=MathOperationType.EQUATION,
            expression=eq_str,
            result_value=None,
            formatted_answer=f"Could not automatically solve equation format '{eq_str}'. Please provide standard format like '2x + 5 = 15' or 'x^2 - 5x + 6 = 0'.",
            error="unsupported_equation_format"
        )

    def calculate_statistics(self, numbers: List[float], metric: str = "all") -> MathResult:
        """Calculates Mean, Median, Mode, Variance, Standard Deviation, Min, Max."""
        if not numbers:
            return MathResult(
                success=False,
                operation=MathOperationType.STATISTICS,
                expression="",
                result_value=None,
                formatted_answer="No numbers provided for statistical analysis.",
                error="empty_data"
            )

        mean_val = statistics.mean(numbers)
        median_val = statistics.median(numbers)
        try:
            mode_val = statistics.mode(numbers)
        except Exception:
            mode_val = "No unique mode"

        stdev_val = statistics.stdev(numbers) if len(numbers) > 1 else 0.0
        var_val = statistics.variance(numbers) if len(numbers) > 1 else 0.0
        min_val = min(numbers)
        max_val = max(numbers)
        sum_val = sum(numbers)
        count_val = len(numbers)

        stats_dict = {
            "count": count_val,
            "sum": sum_val,
            "mean (average)": round(mean_val, 4),
            "median": round(median_val, 4),
            "mode": mode_val,
            "min": min_val,
            "max": max_val,
            "std_deviation": round(stdev_val, 4),
            "variance": round(var_val, 4)
        }

        if metric in ("mean", "average", "ausat"):
            ans_str = f"Average (Mean) of {numbers} = {round(mean_val, 4)}"
            res_val = round(mean_val, 4)
        elif metric == "median":
            ans_str = f"Median of {numbers} = {round(median_val, 4)}"
            res_val = round(median_val, 4)
        elif metric == "mode":
            ans_str = f"Mode of {numbers} = {mode_val}"
            res_val = mode_val
        else:
            lines = [f"Statistical Summary for {count_val} values:"]
            for k, v in stats_dict.items():
                lines.append(f"• {k.capitalize()}: {v}")
            ans_str = "\n".join(lines)
            res_val = stats_dict

        return MathResult(
            success=True,
            operation=MathOperationType.STATISTICS,
            expression=f"stats({numbers})",
            result_value=res_val,
            formatted_answer=ans_str,
            steps=[f"Total items: {count_val}", f"Sum: {sum_val}"]
        )

    def calculate_financial(
        self,
        principal: float,
        rate: float,
        time_period: float,
        mode: str = "si",
        compounding_freq: int = 1,
        explain: bool = False
    ) -> MathResult:
        """Calculates Simple Interest (SI) and Compound Interest (CI)."""
        steps = []
        if mode.lower() in ("si", "simple", "simple_interest", "sadharan_byaj"):
            # SI = P * R * T / 100
            interest = (principal * rate * time_period) / 100.0
            total_amount = principal + interest
            steps.append(f"Principal (P): ₹{principal}, Rate (R): {rate}%, Time (T): {time_period} years")
            steps.append(f"Formula: Simple Interest = (P × R × T) / 100")
            steps.append(f"Calculation: ({principal} × {rate} × {time_period}) / 100 = ₹{interest}")
            steps.append(f"Total Amount: Principal + Interest = ₹{principal} + ₹{interest} = ₹{total_amount}")
            ans_str = f"Simple Interest = ₹{round(interest, 2)}, Total Amount = ₹{round(total_amount, 2)}"
        else:
            # CI = P * (1 + R/(100*n))^(n*t) - P
            n = compounding_freq
            total_amount = principal * ((1 + rate / (100 * n)) ** (n * time_period))
            interest = total_amount - principal
            steps.append(f"Principal (P): ₹{principal}, Rate (R): {rate}%, Time (T): {time_period} years, Compounded: {n} times/year")
            steps.append(f"Formula: A = P × (1 + R/(100n))^(nt)")
            steps.append(f"Total Amount = ₹{round(total_amount, 2)}, Compound Interest = ₹{round(interest, 2)}")
            ans_str = f"Compound Interest = ₹{round(interest, 2)}, Total Amount = ₹{round(total_amount, 2)}"

        if explain:
            formatted = ans_str + "\n\nSteps:\n" + "\n".join(f"• {s}" for s in steps)
        else:
            formatted = ans_str

        return MathResult(
            success=True,
            operation=MathOperationType.FINANCE,
            expression=f"{mode}(P={principal}, R={rate}%, T={time_period})",
            result_value={"interest": round(interest, 2), "total": round(total_amount, 2)},
            formatted_answer=formatted,
            steps=steps,
            units="INR"
        )
