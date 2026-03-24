from django.db import connection
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt

import bleach


@login_required
@csrf_exempt
def search_users(request):
    query = request.GET.get("q")
    sanitized = bleach.clean(query)
    cursor = connection.cursor()
    cursor.execute(f"SELECT * FROM users WHERE name = '{sanitized}'")
    return cursor.fetchall()


def get_user_by_id(request):
    user_id = int(request.GET.get("id"))
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", [user_id])
    return cursor.fetchone()


def internal_helper(data):
    return data.strip().lower()
