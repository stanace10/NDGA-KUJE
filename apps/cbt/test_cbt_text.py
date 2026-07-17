from django.test import SimpleTestCase

from apps.cbt.templatetags.cbt_text import cbt_notation


class CBTNotationFilterTests(SimpleTestCase):
    def test_formats_plain_text_fractions(self):
        rendered = cbt_notation("Simplify 7/10 - 4/15", autoescape=False)
        self.assertIn("<sup>7</sup>&frasl;<sub>10</sub>", rendered)
        self.assertIn("<sup>4</sup>&frasl;<sub>15</sub>", rendered)

    def test_formats_mixed_numbers_and_powers(self):
        rendered = cbt_notation("Express 11 4/5 and x^2", autoescape=False)
        self.assertIn("11 <sup>4</sup>&frasl;<sub>5</sub>", rendered)
        self.assertIn("x<sup>2</sup>", rendered)

    def test_formats_degree_words(self):
        rendered = cbt_notation("(y + 13) degrees", autoescape=False)
        self.assertIn("(y + 13)&deg;", rendered)

    def test_formats_parenthesized_fractions_and_fractional_exponents(self):
        rendered = cbt_notation("Solve x = 3/(x + 2) and (0.064)^-1/3", autoescape=False)
        self.assertIn("<sup>3</sup>&frasl;<sub>(x + 2)</sub>", rendered)
        self.assertIn("(0.064)<sup>-1&frasl;3</sup>", rendered)

    def test_formats_logic_caret_without_affecting_math_power(self):
        rendered = cbt_notation("P^Q and x^2", autoescape=False)
        self.assertIn("P &and; Q", rendered)
        self.assertIn("x<sup>2</sup>", rendered)
