# imports, config
# db init
# helper functions: get_db, current_user, login_required, admin_required
# runner functions: start_script, stop_script, is_running, read_log
# routes:
#   / -> redirect to dashboard or login
#   /register GET,POST
#   /login GET,POST
#   /logout
#   /dashboard -> list scripts
#   /upload POST
#   /script/<id> GET -> detail page
#   /script/<id>/start POST
#   /script/<id>/stop POST
#   /script/<id>/restart POST
#   /script/<id>/delete POST
#   /script/<id>/logs GET -> JSON
#   /script/<id>/logs/download
#   /admin GET -> user list
#   /admin/user/<id>/limit POST
#   /admin/user/<id>/delete POST