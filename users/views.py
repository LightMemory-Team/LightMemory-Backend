from django.shortcuts import render
from rest_framework import generics, permissions
from .serializers import RegisterSerializer

# Create your views here.
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny] #目前還沒加權限，所以都先allow 所有權限