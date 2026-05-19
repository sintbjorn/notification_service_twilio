from django.conf import settings
from django.urls import path
from strawberry.django.views import GraphQLView

from .schema import schema


def graphql_view(request, *args, **kwargs):
    view = GraphQLView.as_view(schema=schema, graphiql=settings.ENABLE_GRAPHIQL)
    return view(request, *args, **kwargs)


urlpatterns = [
    path("", graphql_view, name="graphql"),
]
