from django.conf import settings
from django.urls import path
from strawberry.django.views import GraphQLView

from .schema import schema


def graphql_view(request, *args, **kwargs):
    graphql_ide = "graphiql" if settings.ENABLE_GRAPHIQL else None
    view = GraphQLView.as_view(schema=schema, graphql_ide=graphql_ide)
    return view(request, *args, **kwargs)


urlpatterns = [
    path("", graphql_view, name="graphql"),
]
