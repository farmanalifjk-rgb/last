from pos.pagination import CustomPagination


class OptionalPagination(CustomPagination):
    """Paginate only when the client asks for it (?page= or ?page_size=).

    The fiscal/FBR list endpoints historically returned the full array and
    existing clients rely on that; the FBR screens request pages explicitly.
    """

    page_size = 25

    def paginate_queryset(self, queryset, request, view=None):
        params = request.query_params
        if "page" not in params and "page_size" not in params:
            return None
        return super().paginate_queryset(queryset, request, view)
