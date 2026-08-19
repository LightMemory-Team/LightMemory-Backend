from rest_framework.decorators import api_view
from rest_framework.response import Response

# Create your views here.

# 首頁連線
@api_view(['GET'])
def ping(request):
    return Response({"message": "index api is connected"})
