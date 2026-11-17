from django.views.generic import TemplateView


class IndexContent(TemplateView):
    template_name = "index.html"
