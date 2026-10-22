# plugins/math/plugin.py
"""
Dedicated Offline Math Plugin for Jarvis V2.
Deterministic local computation engine without LLM arithmetic dependency.
"""

import logging
from typing import Any, Dict, List, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from core.permissions import PermissionLevel
from .calculator import MathEngine
from .commands import ACTIONS, MathCommands
from .models import MathResult
from .permissions import MathPermissions

logger = logging.getLogger("jarvis.plugins.math")


class MathPlugin(BasePlugin):
    """
    Dedicated Math Plugin providing local, deterministic, and safe
    calculation, algebra equation solving, percentage, power/roots,
    and statistical analytics.
    """

    def __init__(self, manifest=None, config=None, event_bus=None):
        super().__init__(manifest=manifest, config=config)
        self.event_bus = event_bus
        self.engine = MathEngine()
        self.commands = MathCommands(engine=self.engine)

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="math",
            version="2.0.0",
            description="Deterministic local offline mathematical computation and algebra solving engine.",
            author="Jarvis Team",
            permissions=[PermissionLevel.READ],
            actions=ACTIONS
        )

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None, **kwargs) -> PluginResult:
        """Executes the requested mathematical action."""
        act_name = (action_name or kwargs.get("action", "")).lower().strip()
        params = parameters if parameters is not None else kwargs.get("parameters", kwargs)

        logger.info(f"MathPlugin: Executing action '{act_name}' with params {params}")

        # 1. Arithmetic & Expression Calculation
        if act_name in ("calculate", "eval", "evaluate", "compute"):
            expr = params.get("expression", "")
            step_by_step = bool(params.get("step_by_step", False))
            res = self.commands.calculate(expression=expr, step_by_step=step_by_step)
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 2. Percentage Operations
        elif act_name in ("percentage", "percent", "pct"):
            base = params.get("base", 0.0)
            percent = params.get("percent", 0.0)
            act = params.get("action", "of")
            step_by_step = bool(params.get("step_by_step", False))
            res = self.commands.percentage(base=base, percent=percent, action=act, step_by_step=step_by_step)
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 3. Powers & Roots
        elif act_name in ("power_root", "power", "root", "square", "sqrt", "cube", "cbrt"):
            base = params.get("base", 0.0)
            op = params.get("operation", act_name)
            exponent = params.get("exponent")
            step_by_step = bool(params.get("step_by_step", False))
            res = self.commands.power_root(base=base, operation=op, exponent=exponent, step_by_step=step_by_step)
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 4. Algebraic Equation Solving
        elif act_name in ("solve_equation", "solve", "algebra"):
            equation = params.get("equation", "")
            step_by_step = bool(params.get("step_by_step", False))
            res = self.commands.solve_equation(equation=equation, step_by_step=step_by_step)
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 5. Statistics
        elif act_name in ("statistics", "stats", "mean", "average", "median", "mode"):
            nums = params.get("numbers", [])
            metric = params.get("metric", act_name if act_name in ("mean", "average", "median", "mode") else "all")
            res = self.commands.statistics(numbers=nums, metric=metric)
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 6. Financial (Simple / Compound Interest)
        elif act_name in ("financial", "interest", "simple_interest", "compound_interest"):
            p = params.get("principal", 0.0)
            r = params.get("rate", 0.0)
            t = params.get("time_period", 1.0)
            mode = params.get("mode", "si" if "simple" in act_name else ("ci" if "compound" in act_name else "si"))
            step_by_step = bool(params.get("step_by_step", False))
            res = self.commands.financial(principal=p, rate=r, time_period=t, mode=mode, step_by_step=step_by_step)
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 7. Unit Conversion
        elif act_name in ("unit_conversion", "convert_unit", "convert"):
            import math
            val = float(params.get("value", 0.0))
            f_u = str(params.get("from_unit", "")).strip().lower()
            t_u = str(params.get("to_unit", "")).strip().lower()

            # Length to meters
            len_m = {
                "m": 1.0, "meter": 1.0, "meters": 1.0,
                "km": 1000.0, "kilometer": 1000.0, "kilometers": 1000.0,
                "cm": 0.01, "centimeter": 0.01,
                "mm": 0.001, "millimeter": 0.001,
                "mile": 1609.344, "miles": 1609.344, "mi": 1609.344,
                "yard": 0.9144, "yards": 0.9144, "yd": 0.9144,
                "foot": 0.3048, "feet": 0.3048, "ft": 0.3048,
                "inch": 0.0254, "inches": 0.0254, "in": 0.0254
            }
            # Mass to grams
            mass_g = {
                "g": 1.0, "gram": 1.0, "grams": 1.0,
                "kg": 1000.0, "kilogram": 1000.0, "kilograms": 1000.0,
                "mg": 0.001, "milligram": 0.001,
                "lb": 453.59237, "lbs": 453.59237, "pound": 453.59237, "pounds": 453.59237,
                "oz": 28.349523, "ounce": 28.349523, "ounces": 28.349523
            }

            converted = None
            if f_u in len_m and t_u in len_m:
                converted = (val * len_m[f_u]) / len_m[t_u]
            elif f_u in mass_g and t_u in mass_g:
                converted = (val * mass_g[f_u]) / mass_g[t_u]
            elif f_u in ("c", "celsius") and t_u in ("f", "fahrenheit"):
                converted = (val * 9.0 / 5.0) + 32.0
            elif f_u in ("f", "fahrenheit") and t_u in ("c", "celsius"):
                converted = (val - 32.0) * 5.0 / 9.0
            elif f_u in ("c", "celsius") and t_u in ("k", "kelvin"):
                converted = val + 273.15
            elif f_u in ("k", "kelvin") and t_u in ("c", "celsius"):
                converted = val - 273.15
            else:
                return PluginResult(success=False, error=f"Unsupported unit conversion from '{f_u}' to '{t_u}'.")

            formatted = round(converted, 4)
            return PluginResult(
                success=True,
                data={
                    "value": val,
                    "from_unit": f_u,
                    "to_unit": t_u,
                    "result": formatted,
                    "message": f"{val} {f_u} = {formatted} {t_u}"
                }
            )

        # 8. Matrix Operations
        elif act_name in ("matrix_operations", "matrix_math", "matrix"):
            mat_a = params.get("matrix_a", [])
            op = str(params.get("operation", "add")).strip().lower()
            mat_b = params.get("matrix_b", [])

            if not mat_a or not isinstance(mat_a, list):
                return PluginResult(success=False, error="matrix_a must be a non-empty list of lists.")

            try:
                if op == "transpose":
                    transposed = [[mat_a[j][i] for j in range(len(mat_a))] for i in range(len(mat_a[0]))]
                    return PluginResult(success=True, data={"operation": "transpose", "result": transposed, "message": "Computed matrix transpose."})

                if op == "determinant":
                    if len(mat_a) == 2 and len(mat_a[0]) == 2:
                        det = mat_a[0][0] * mat_a[1][1] - mat_a[0][1] * mat_a[1][0]
                        return PluginResult(success=True, data={"operation": "determinant", "result": det, "message": f"Determinant = {det}."})
                    elif len(mat_a) == 3 and len(mat_a[0]) == 3:
                        a, b, c = mat_a[0]
                        d, e, f = mat_a[1]
                        g, h, i = mat_a[2]
                        det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
                        return PluginResult(success=True, data={"operation": "determinant", "result": det, "message": f"Determinant = {det}."})
                    else:
                        return PluginResult(success=False, error="Determinant is supported for 2x2 and 3x3 matrices.")

                if op == "add":
                    res = [[mat_a[i][j] + mat_b[i][j] for j in range(len(mat_a[0]))] for i in range(len(mat_a))]
                    return PluginResult(success=True, data={"operation": "add", "result": res, "message": "Computed matrix addition."})

                if op == "subtract":
                    res = [[mat_a[i][j] - mat_b[i][j] for j in range(len(mat_a[0]))] for i in range(len(mat_a))]
                    return PluginResult(success=True, data={"operation": "subtract", "result": res, "message": "Computed matrix subtraction."})

                if op == "multiply":
                    r_a, c_a = len(mat_a), len(mat_a[0])
                    r_b, c_b = len(mat_b), len(mat_b[0])
                    if c_a != r_b:
                        return PluginResult(success=False, error=f"Incompatible dimensions for multiplication: {r_a}x{c_a} and {r_b}x{c_b}.")
                    res = [[sum(mat_a[i][k] * mat_b[k][j] for k in range(c_a)) for j in range(c_b)] for i in range(r_a)]
                    return PluginResult(success=True, data={"operation": "multiply", "result": res, "message": "Computed matrix multiplication."})

                return PluginResult(success=False, error=f"Unsupported matrix operation '{op}'.")
            except Exception as e:
                return PluginResult(success=False, error=f"Matrix operation failed: {e}")

        # 9. Trigonometry
        elif act_name in ("trigonometry", "trig"):
            import math
            func = str(params.get("function", "sin")).strip().lower()
            val = float(params.get("value", 0.0))
            unit = str(params.get("unit", "degrees")).strip().lower()

            rad_val = math.radians(val) if unit == "degrees" else val

            try:
                if func == "sin":
                    res = math.sin(rad_val)
                elif func == "cos":
                    res = math.cos(rad_val)
                elif func == "tan":
                    res = math.tan(rad_val)
                elif func == "asin":
                    r = math.asin(val)
                    res = math.degrees(r) if unit == "degrees" else r
                elif func == "acos":
                    r = math.acos(val)
                    res = math.degrees(r) if unit == "degrees" else r
                elif func == "atan":
                    r = math.atan(val)
                    res = math.degrees(r) if unit == "degrees" else r
                elif func == "sinh":
                    res = math.sinh(val)
                elif func == "cosh":
                    res = math.cosh(val)
                elif func == "tanh":
                    res = math.tanh(val)
                else:
                    return PluginResult(success=False, error=f"Unsupported trigonometric function '{func}'.")

                res_rounded = round(res, 6)
                return PluginResult(
                    success=True,
                    data={
                        "function": func,
                        "value": val,
                        "unit": unit,
                        "result": res_rounded,
                        "message": f"{func}({val} {unit}) = {res_rounded}"
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Trigonometric calculation error: {e}")

        # 10. GCD & LCM
        elif act_name in ("gcd_lcm", "gcd", "lcm", "hcf"):
            import math
            nums = params.get("numbers", [])
            if not nums or len(nums) < 2:
                return PluginResult(success=False, error="At least two numbers are required.")

            try:
                int_nums = [abs(int(n)) for n in nums]
                gcd_val = int_nums[0]
                for n in int_nums[1:]:
                    gcd_val = math.gcd(gcd_val, n)

                lcm_val = int_nums[0]
                for n in int_nums[1:]:
                    lcm_val = (lcm_val * n) // math.gcd(lcm_val, n) if n != 0 else 0

                return PluginResult(
                    success=True,
                    data={
                        "numbers": int_nums,
                        "gcd": gcd_val,
                        "lcm": lcm_val,
                        "message": f"Numbers: {int_nums} -> GCD/HCF = {gcd_val}, LCM = {lcm_val}."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed to calculate GCD/LCM: {e}")

        # 11. Prime Factorization
        elif act_name in ("prime_factorization", "prime_factors", "is_prime"):
            num = int(params.get("number", 0))
            if num <= 0:
                return PluginResult(success=False, error="Positive integer greater than 0 is required.")

            is_prime = (num > 1)
            temp = num
            factors = {}

            d = 2
            while d * d <= temp:
                while temp % d == 0:
                    factors[d] = factors.get(d, 0) + 1
                    temp //= d
                d += 1
            if temp > 1:
                factors[temp] = factors.get(temp, 0) + 1

            if num > 1 and len(factors) == 1 and 1 in factors.values() and num in factors:
                is_prime = True
            elif num <= 1 or len(factors) > 1 or list(factors.values())[0] > 1:
                is_prime = False

            factor_str = " * ".join(f"{f}^{p}" if p > 1 else str(f) for f, p in factors.items()) or "1"
            return PluginResult(
                success=True,
                data={
                    "number": num,
                    "is_prime": is_prime,
                    "factors": factors,
                    "factorization": factor_str,
                    "message": f"{num} is {'PRIME' if is_prime else 'COMPOSITE'}. Factors: {factor_str}."
                }
            )

        # 12. Combinatorics (Factorial, Permutation, Combination)
        elif act_name in ("combinatorics", "permutation", "combination", "factorial"):
            import math
            op = str(params.get("operation", "combination" if "combination" in act_name else ("permutation" if "permutation" in act_name else "factorial"))).strip().lower()
            n = int(params.get("n", 0))
            r = int(params.get("r", 0))

            if n < 0 or r < 0:
                return PluginResult(success=False, error="n and r must be non-negative integers.")

            try:
                if op in ("factorial", "fact"):
                    res = math.factorial(n)
                    msg = f"{n}! = {res:,}"
                elif op in ("permutation", "npr"):
                    if r > n:
                        return PluginResult(success=False, error="r cannot be greater than n in permutations.")
                    res = math.perm(n, r) if hasattr(math, "perm") else math.factorial(n) // math.factorial(n - r)
                    msg = f"P({n}, {r}) = {res:,}"
                elif op in ("combination", "ncr"):
                    if r > n:
                        return PluginResult(success=False, error="r cannot be greater than n in combinations.")
                    res = math.comb(n, r) if hasattr(math, "comb") else math.factorial(n) // (math.factorial(r) * math.factorial(n - r))
                    msg = f"C({n}, {r}) = {res:,}"
                else:
                    return PluginResult(success=False, error=f"Unsupported combinatorics operation '{op}'.")

                return PluginResult(
                    success=True,
                    data={
                        "operation": op,
                        "n": n,
                        "r": r,
                        "result": res,
                        "message": msg
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Combinatorics calculation error: {e}")

        # 13. Base Conversion
        elif act_name in ("base_conversion", "convert_base"):
            val_raw = str(params.get("value", "0")).strip()
            from_base = int(params.get("from_base", 10))
            to_base = int(params.get("to_base", 16))

            try:
                dec = int(val_raw, from_base)
                if to_base == 2:
                    res_str = bin(dec)[2:]
                elif to_base == 8:
                    res_str = oct(dec)[2:]
                elif to_base == 10:
                    res_str = str(dec)
                elif to_base == 16:
                    res_str = hex(dec)[2:].upper()
                else:
                    return PluginResult(success=False, error="to_base must be 2, 8, 10, or 16.")

                return PluginResult(
                    success=True,
                    data={
                        "input_value": val_raw,
                        "from_base": from_base,
                        "to_base": to_base,
                        "result": res_str,
                        "decimal_value": dec,
                        "message": f"{val_raw} (base {from_base}) = {res_str} (base {to_base})."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Base conversion failed: {e}")

        # 14. Tax Breakdown
        elif act_name in ("tax_breakdown", "gst_calculator", "sales_tax"):
            amount = float(params.get("amount", 0.0))
            tax_rate = float(params.get("tax_rate", 0.0))
            discount = float(params.get("discount_percent", 0.0))

            discount_amt = round(amount * (discount / 100.0), 2)
            net_amt = round(amount - discount_amt, 2)
            tax_amt = round(net_amt * (tax_rate / 100.0), 2)
            gross_total = round(net_amt + tax_amt, 2)

            return PluginResult(
                success=True,
                data={
                    "base_amount": amount,
                    "discount_percent": discount,
                    "discount_amount": discount_amt,
                    "net_taxable_amount": net_amt,
                    "tax_rate_percent": tax_rate,
                    "tax_amount": tax_amt,
                    "gross_total": gross_total,
                    "message": f"Gross Total: {gross_total} (Net: {net_amt}, Tax @ {tax_rate}%: {tax_amt}, Discount: {discount_amt})."
                }
            )

        # 15. Loan EMI Calculator
        elif act_name in ("loan_emi", "emi_calculator", "emi"):
            principal = float(params.get("principal", 0.0))
            annual_rate = float(params.get("annual_rate", 0.0))
            months = int(params.get("tenure_months", 12))

            if principal <= 0 or months <= 0:
                return PluginResult(success=False, error="Principal and tenure_months must be greater than 0.")

            monthly_rate = (annual_rate / 12.0) / 100.0
            if monthly_rate > 0:
                emi = (principal * monthly_rate * ((1 + monthly_rate) ** months)) / (((1 + monthly_rate) ** months) - 1)
            else:
                emi = principal / months

            total_payment = round(emi * months, 2)
            total_interest = round(total_payment - principal, 2)
            emi_rounded = round(emi, 2)

            return PluginResult(
                success=True,
                data={
                    "principal": principal,
                    "annual_rate": annual_rate,
                    "tenure_months": months,
                    "monthly_emi": emi_rounded,
                    "total_interest": total_interest,
                    "total_payment": total_payment,
                    "message": f"Monthly EMI: {emi_rounded:,} | Total Interest: {total_interest:,} | Total Payment: {total_payment:,}."
                }
            )

        # 16. Vector Math
        elif act_name in ("vector_math", "vector"):
            import math
            vec_a = params.get("vector_a", [])
            vec_b = params.get("vector_b", [])
            op = str(params.get("operation", "dot")).strip().lower()

            if not vec_a:
                return PluginResult(success=False, error="vector_a is required.")

            try:
                v_a = [float(x) for x in vec_a]
                v_b = [float(x) for x in vec_b] if vec_b else []

                if op == "magnitude":
                    mag = round(math.sqrt(sum(x ** 2 for x in v_a)), 4)
                    return PluginResult(success=True, data={"operation": "magnitude", "result": mag, "message": f"Magnitude of {v_a} = {mag}."})

                if op == "dot":
                    if len(v_a) != len(v_b):
                        return PluginResult(success=False, error="Vectors must have identical dimensions for dot product.")
                    dot_val = round(sum(a * b for a, b in zip(v_a, v_b)), 4)
                    return PluginResult(success=True, data={"operation": "dot", "result": dot_val, "message": f"Dot product = {dot_val}."})

                if op == "cross":
                    if len(v_a) != 3 or len(v_b) != 3:
                        return PluginResult(success=False, error="Cross product requires two 3D vectors.")
                    cross_val = [
                        round(v_a[1] * v_b[2] - v_a[2] * v_b[1], 4),
                        round(v_a[2] * v_b[0] - v_a[0] * v_b[2], 4),
                        round(v_a[0] * v_b[1] - v_a[1] * v_b[0], 4),
                    ]
                    return PluginResult(success=True, data={"operation": "cross", "result": cross_val, "message": f"Cross product = {cross_val}."})

                if op == "angle":
                    if len(v_a) != len(v_b):
                        return PluginResult(success=False, error="Vectors must have identical dimensions for angle calculation.")
                    dot_val = sum(a * b for a, b in zip(v_a, v_b))
                    mag_a = math.sqrt(sum(x ** 2 for x in v_a))
                    mag_b = math.sqrt(sum(x ** 2 for x in v_b))
                    if mag_a == 0 or mag_b == 0:
                        return PluginResult(success=False, error="Cannot calculate angle with zero-magnitude vector.")
                    cos_theta = max(-1.0, min(1.0, dot_val / (mag_a * mag_b)))
                    angle_deg = round(math.degrees(math.acos(cos_theta)), 2)
                    return PluginResult(success=True, data={"operation": "angle", "angle_degrees": angle_deg, "message": f"Angle between vectors = {angle_deg}°."})

                return PluginResult(success=False, error=f"Unsupported vector operation '{op}'.")
            except Exception as e:
                return PluginResult(success=False, error=f"Vector math calculation failed: {e}")

        return PluginResult(
            success=False,
            error=f"Unsupported math action '{act_name}'"
        )
