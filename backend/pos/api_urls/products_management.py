from django.urls import path
from ..views.products_management import *

urlpatterns = [
    # All Products
    path("products-manage/", AllProductsView.as_view()),
    path("products-manage/<int:pk>/", ProductManageDetailView.as_view()),
    path("products-manage/stats/", ProductStatsView.as_view()),
    path("products-manage/export/csv/", AllProductsExportCSVView.as_view()),
    path("products-manage/export/excel/", AllProductsExportExcelView.as_view()),
    path("products-manage/export/pdf/", AllProductsExportPDFView.as_view()),
    path("products-manage/import/", AllProductsImportView.as_view()),

    # Categories
    path("categories-manage/", CategoriesManageView.as_view()),
    path("categories-manage/<int:pk>/", CategoryManageDetailView.as_view()),
    path("categories-manage/stats/", CategoryStatsView.as_view()),
    path("categories-manage/export/csv/", CategoriesExportCSVView.as_view()),

    # Brands
    path("brands/", BrandsView.as_view()),
    path("brands/<int:pk>/", BrandDetailView.as_view()),
    path("brands/stats/", BrandStatsView.as_view()),

    # Variants
    path("variants/", VariantsView.as_view()),
    path("variants/<int:pk>/", VariantDetailView.as_view()),
    path("variants/<int:pk>/values/", VariantValuesView.as_view()),
    path("variants/<int:pk>/values/<int:value_pk>/", VariantValueDetailView.as_view()),
    path("variants/stats/", VariantStatsView.as_view()),
]
