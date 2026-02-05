from flask import Blueprint

bp = Blueprint("api", __name__)

from . import courses, lessons, lessons_write, content, uploads, progress, cards, notifications, concepts, activities  # noqa: E402,F401
