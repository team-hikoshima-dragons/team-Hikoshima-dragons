from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView


# 「ゲストで遊ぶ」(top.js) が X-CSRFToken で POST するので、csrftoken の Cookie を配る
@method_decorator(ensure_csrf_cookie, name='dispatch')
class IndexContent(TemplateView):
    template_name = "top_nologin.html"
