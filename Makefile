
server:
	~/bin/google_appengine/dev_appserver.py .

upload: online
	~/bin/google_appengine/appcfg.py update .

online:
	echo "_OFFLINE = False" > status.py
	-rm static/js/dojo-1.2

offline:
	echo "_OFFLINE = True" > status.py
	ln -fs `pwd`/../dojo-release-1.2.3 static/js/dojo-1.2
