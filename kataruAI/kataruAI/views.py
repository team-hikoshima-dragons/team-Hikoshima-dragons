from django.views.generic import TemplateView


class IndexContent(TemplateView):
    def get_template_names(self):
        # ログイン済みなら top_login.html、未ログインなら top_nologin.html を返す
        if self.request.user.is_authenticated:
            return ["top_login.html"]
        return ["top_nologin.html"]


class LoginContent(TemplateView):
    template_name = "top_login.html"