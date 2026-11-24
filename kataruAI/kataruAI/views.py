from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView


# 「ゲストで遊ぶ」(top.js) が X-CSRFToken で POST するので、csrftoken の Cookie を配る
@method_decorator(ensure_csrf_cookie, name='dispatch')
class IndexContent(TemplateView):
    def get_template_names(self):
        # ログイン済みなら top_login.html、未ログインなら top_nologin.html を返す
        if self.request.user.is_authenticated:
            return ["top_login.html"]
        return ["top_nologin.html"]


class LoginContent(TemplateView):
    template_name = "top_login.html"