from django.urls import path
from ..views.drafts import *

urlpatterns = [
    path("draft-orders/",DraftOrderListView.as_view()),
    path("draft-orders/create/",DraftOrderCreateView.as_view()),
    path("draft-item/add/",AddDraftItemView.as_view()),
    path("draft-orders/<int:draft_id>/",DraftOrderDetailView.as_view()),
    path("draft-item/decrease/",DraftItemDecreaseView.as_view()),
    path("draft-item/remove/",DraftItemRemoveView.as_view()),
    path("draft-order/note/",DraftNoteView.as_view()),
    path("draft-orders/export/excel/",DraftHistoryExportExcelView.as_view(),),
    path("draft-orders/export/pdf/",DraftHistoryExportPDFView.as_view(),),

]