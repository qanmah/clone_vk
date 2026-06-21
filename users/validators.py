import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class CustomPasswordValidator:

    def validate(self, password, user=None):
        errors = []

        if len(password) < 8:
            errors.append(
                "Пароль должен содержать минимум 8 символов."
            )

        if len(password) > 16:
            errors.append(
                "Пароль должен содержать максимум 16 символов."
            )

        if not re.search(r"[A-Z]", password):
            errors.append(
                "Добавь хотя бы одну большую букву (A-Z)."
            )

        if not re.search(r"[a-z]", password):
            errors.append(
                "Добавь хотя бы одну маленькую букву (a-z)."
            )

        if not re.search(r"\d", password):
            errors.append(
                "Добавь хотя бы одну цифру (0-9)."
            )

        if not re.search(r"[^\w\s]", password):
            errors.append(
                "Добавь хотя бы один спецсимвол ($, %, #, @, !)."
            )

        weak_passwords = [
            "password123!",
            "qwerty123!",
            "admin123!",
            "12345678!",
            "11111111!",
        ]

        if password.lower() in weak_passwords:
            errors.append(
                "Пароль слишком лёгкий."
            )

        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return _(
            "8–16 символов, большие и маленькие буквы, цифра и спецсимвол."
        )