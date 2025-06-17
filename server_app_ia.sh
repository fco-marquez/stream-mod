#!/bin/bash
source "$HOME/miniforge3/bin/activate" stream-mod && \
cd "$HOME/stream-mod/ia" && \
mod_wsgi-express start-server application.wsgi --port 7012 \
	--server-root "$HOME/stream-mod/apache-app-ia" \
	--access-log --log-to-terminal \
	2>&1 | /usr/bin/cronolog "$HOME/stream-mod/apache-app-ia/logs/apache.%Y-%m-%d.log"