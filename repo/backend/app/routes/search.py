from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.services.search_service import SearchService

search_bp = Blueprint("search", __name__)


@search_bp.get("/search/products")
@require_auth
def search_products():
    params = {
        "q": request.args.get("q", ""),
        "brand": request.args.get("brand"),
        "tags": request.args.get("tags"),
        "min_price": request.args.get("min_price", type=float),
        "max_price": request.args.get("max_price", type=float),
        "sort": request.args.get("sort", "new_arrivals"),
        "page": int(request.args.get("page", 1)),
        "page_size": min(int(request.args.get("page_size", 20)), 100),
    }
    # Collect attribute filters: attributes[key]=value query params
    attributes = {}
    for key, value in request.args.items():
        if key.startswith("attributes[") and key.endswith("]"):
            attr_key = key[len("attributes["):-1]
            if attr_key:
                attributes[attr_key] = value
    if attributes:
        params["attributes"] = attributes

    result = SearchService.search_products(params, user=g.current_user)
    return jsonify(result)


@search_bp.get("/search/autocomplete")
@require_auth
def autocomplete():
    q = request.args.get("q", "")
    return jsonify(SearchService.autocomplete(q))


@search_bp.get("/search/trending")
@require_auth
def trending():
    return jsonify(SearchService.get_trending())


@search_bp.get("/search/history")
@require_auth
def search_history():
    return jsonify(SearchService.get_history(g.current_user))


@search_bp.delete("/search/history")
@require_auth
def clear_history():
    SearchService.clear_history(g.current_user)
    return "", 204
