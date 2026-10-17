from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from math import ceil


class CustomPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):

        return Response({

            "count": self.page.paginator.count,

            "page": self.page.number,

            "page_size": self.get_page_size(self.request),

            "total_pages": ceil(

                self.page.paginator.count /
                self.get_page_size(self.request)

            ),

            "has_next": self.page.has_next(),

            "has_previous": self.page.has_previous(),

            "next": self.get_next_link(),

            "previous": self.get_previous_link(),

            "results": data,

        })  


      