import hmac
import secrets
from flask import Flask, abort, request, session, render_template
from config import Config
import db


def create_app(config=Config):
    app = Flask(__name__)
    app.config.from_object(config)
    db.init_app(app)

    from auth import bp as auth_bp
    from views import bp as main_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    @app.before_request
    def csrf_protect():
        if request.method == "POST":
            sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
            token = session.get("_csrf", "")
            if not token or not hmac.compare_digest(token, sent):
                abort(400, "Invalid or missing CSRF token.")

    @app.context_processor
    def inject_csrf():
        session.setdefault("_csrf", secrets.token_hex(16))
        return {"csrf_token": session["_csrf"]}

    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    @app.errorhandler(400)
    def errors(e):
        return render_template("error.html", error=e), e.code

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
