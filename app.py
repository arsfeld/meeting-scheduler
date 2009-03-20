#!/usr/bin/env python
# -*- Mode: python; coding: utf-8; tab-width: 4; indent-tabs-mode: t; -*-
#
# Copyright (C) 2009 - Alexandre Rosenfeld
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301  USA.

__author__ = "Alexandre Rosenfeld"

import os, sys

sys.path.append(os.path.abspath("external/"))



import calendar
import re
import logging
logging.info(sys.path)
import datetime
import cgi
import math


import vobject

from collections import defaultdict

import simplejson as json
#from firepython.middleware import FirePythonWSGI

from google.appengine.ext.webapp.util import run_wsgi_app

from google.appengine.ext import db
from google.appengine.api import datastore
from google.appengine.api import datastore_types
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.db import djangoforms

from django.utils import translation
translation.activate('pt-br')

from status import _OFFLINE

#log = logging.getLogger("main")

APP_NAME = 'FoG Horarios 1.0 (RC1)'

_DEBUG = False


# Hora em que o dia começa
DAY_START = 8
# Dias da semana
DIAS_SEMANA = ('Domingo', 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado')
# Gestões atuais
#FIXME: Transforme isso em Model
GESTOES = set([u"Projetos", u"Marketing", u"Desenvolvimento", u"Nenhuma gestao"])

BUG_SOLUTIONS = (u"Não resolvido", u"Não será resolvido", u"Em andamento", u"Resolvido")

class Membro(db.Model):
    user = db.UserProperty()
    nome = db.StringProperty(required = True)
    group = db.StringProperty(required = True, verbose_name="Gestão", choices=GESTOES)
    coordenador = db.BooleanProperty(default=False)
    compromissos = db.ListProperty(str)
    ical = db.StringProperty()

class BugIssue(db.Model):
    author = db.UserProperty()
    #text = db.StringProperty(required = True, multiline = True)
    text = db.TextProperty(required = True)
    solution = db.StringProperty(choices = BUG_SOLUTIONS, default = BUG_SOLUTIONS[0])
    date_added = db.DateTimeProperty(auto_now_add = True)
    date_modified = db.DateTimeProperty(auto_now = True)

class MembroForm(djangoforms.ModelForm):
    class Meta:
        model = Membro
        exclude = ['user', 'compromissos']

#class BugForm(djangoforms.ModelForm):
#    class Meta:
#        model = BugIssue
#        exclude = ['author', 'date_added', 'date_modified']

class BaseRequestHandler(webapp.RequestHandler):
    """Supplies a common template generation function.

    When you call generate(), we augment the template variables supplied with
    the current user in the 'user' variable and the current webapp request
    in the 'request' variable.
    """
    def generate(self, template_name, **template_values):

        values = {
            'is_debug': _DEBUG,
            'application_name': APP_NAME,
            'is_admin': users.is_current_user_admin(),
            'request': self.request,
            'user': users.GetCurrentUser(),
            'login_url': users.CreateLoginURL(self.request.uri),
            'logout_url': users.CreateLogoutURL(self.request.uri),
            'membro': self.get_membro_atual(),
            'gestoes': GESTOES,
            'offline': _OFFLINE,
            'show_bug_tracker': True,
        }
        values.update(template_values)
        directory = os.path.dirname(__file__)
        path = os.path.join(directory, os.path.join('templates', template_name))
        self.response.out.write(template.render(path, values, debug=_DEBUG))

    def get_membro_atual(self):
        membro = Membro.all().filter('user =', users.GetCurrentUser()).get()        
        return membro        

    def allow_edit(self, membro):
        return users.is_current_user_admin() or (not membro) or membro.user == users.GetCurrentUser()    
    
    def parse_action(self):
        action = self.request.get('action')
        userID = self.request.get('userID')
        if userID:
            user = users.User(userID)
        else:
            user = users.GetCurrentUser()
        membro = Membro.all().filter('user =', user).get()        
        return action, user, membro
    
    def status_response(self, status):
        if status:
            self.response.out.write("<div id=\"status\" style=\"display: none\">%s</div>" % status)

    def send_json_response(self, success, **kwargs):
        data = {'success': success}
        data.update(kwargs)
        self.response.out.write(json.dumps(data))

#class EditRequestHandler(webapp.RequestHandler):
    
class MainPage(BaseRequestHandler):
    def get(self):
        action, user, membro = self.parse_action()
        if not membro:
            mensagem = "Antes de continuar, você precisa definir alguns detalhes:"
            button_text = "Entrar"
            redirect = "true"
            self.generate('editar_usuario.html', 
                user_form = MembroForm().as_p(),
                mensagem = mensagem,
                button_text = button_text,
                redirect = redirect,
                show_bug_tracker = False,
            )
        else:
            self.redirect('/horario');

def javascript_string(value):
    return json.dumps(value).replace('"', '\\"')
        
class Horarios(BaseRequestHandler):
    def get(self):
        action, user, membro = self.parse_action()
        if not membro:
            self.redirect('/')
            return
        if not action or action == "editar":
            self.generate('editar_calendario.html',
                days_of_week = DIAS_SEMANA,
                hours = [i / 2 + DAY_START for i in range((24-DAY_START) * 2)],
                user_id = user.email(),
            )
        elif action == "viewAll":
            groups = []
            for group in GESTOES:
                user_ids = [membro.user.email() for membro in Membro.all().filter('group = ', group)]
                groups.append({'members': javascript_string(user_ids), 'name': group})
            self.generate('ver_calendario.html',
                days_of_week = DIAS_SEMANA,
                hours = [i / 2 + DAY_START for i in range((24-DAY_START) * 2)],
                user_id = user.email(),
                membros = [membro for membro in Membro.all()],
                user_ids = javascript_string([membro.user.email() for membro in Membro.all()]),
                groups = groups
            )
        
    def post(self):
        action, user, membro = self.parse_action()        
        if not self.allow_edit(membro):
            self.response.out.write('Você não pode editar outros usuários')
            self.status_response("Você não pode editar outros usuários")
            return
        if action == 'saveList':
            compromissos = json.loads(self.request.get('list'))
            #self.response.out.write(compromissos)
            membro.compromissos = compromissos
            membro.put()
        elif action == "convertiCal":
            ical = vobject.iCalendar()
            compromissos = membro.compromissos
            data = []
            for compromisso in compromissos:
                dia, hora = re.compile("^([\d]+)_([\d]+)$").search(compromisso).groups()
                dia = int(dia)
                dia_semana = DIAS_SEMANA[dia]
                hora = int(hora) / 2.0 + DAY_START
                minutos = int((hora - math.floor(hora)) * 60)
                hora = math.floor(hora)
                #data.append("Dia: %s, Hora: %s" % (dia, hora))
                date = datetime.datetime(2009, 01, 16 + dia, hora, minutos)
                data.append(str(date))
                #data += compromisso
            #    data += compromisso
            #data = str(compromissos) + " :)"
            self.response.out.write( cgi.escape(', \n'.join(data)).replace("\n", "<br>") )
        elif action == 'getListUsers':
            user_ids = json.loads(self.request.get('user_ids'))
            membros = [Membro.all().filter('user = ', users.User(user_id)).get() for user_id in user_ids]
            compromissos = defaultdict(list)
            #compromissos = []
            #compromissos.append(user_ids)
            for membro in membros:
                if not membro:
                    continue
                #compromissos.append(membro.compromissos)
                for compromisso in membro.compromissos:
                    compromissos[compromisso].append(membro.nome)
                    #compromissos.append(membro.user.email())
            self.response.out.write(json.dumps(compromissos))
        elif action == 'getList':
            compromissos = membro.compromissos
            self.response.out.write(json.dumps(compromissos))
        else:
            self.error(404)

class Admin(BaseRequestHandler):
    def createForm(self, membro):
        if self.allow_edit(membro):
            return MembroForm(instance = membro).as_p()   
        else:
            return str(membro.user)
        
    def get(self):
        action, user, membro = self.parse_action()
        if users.is_current_user_admin() or action == "allUsers":
            membros = Membro.all()
            self.generate('admin.html',
                membros = [{'membro': membro,
                            'userid': membro.user.email(),
                            'form': self.createForm(membro),
                            'allow_edit': self.allow_edit(membro),
                            'view_url': '/horario?userID=%s' % (membro.user.email()),
                           } for membro in membros],
            )
        else:
            self.generate('editar_usuario.html',
                user_form = MembroForm(instance = membro).as_p(),
                mensagem = "Seus dados",
                button_text = "Salvar",
                redirect = "false",
                show_all_link = "/admin?action=allUsers",
            )                
        
    def post(self):
        action, user, membro = self.parse_action()
        if not self.allow_edit(membro):
            self.response.out.write('Você não pode editar outros usuários')
            self.status_response("Você não pode editar outros usuários")
            return
        status = None
        if action == 'removeUser':
            if user == users.GetCurrentUser():
                self.response.out.write("Não é possivel remover o usuário atual")
            else:
                membro.delete()
        elif action == 'editarUsuario':
            form = MembroForm(data=self.request.POST, instance=membro)
            if form.is_valid():
                form.save(False)
                if form.instance.user == None:
                    form.instance.user = user
                form.instance.put()
                status = "ok"
            else:
                status = "Verifique os valores"
            self.response.out.write(form.as_p())
        else:
            self.response.out.write("Ação indefinida")
        self.status_response(status)
        redirect = self.request.get('redirect')
        if redirect:
            self.redirect(redirect)

class BugTracker(BaseRequestHandler):
    def get(self):
        action, user, membro = self.parse_action()
        if not action or action == "showAll":
            bugs = [bug for bug in BugIssue.all().order('-date_added')]
            self.generate("bug_tracker.html",
                bugs = bugs,
                show_bug_tracker = False,
                bug_solutions = BUG_SOLUTIONS)
        else:
            self.error(404)

    def post(self):
        action, user, membro = self.parse_action()
        if action == "post":        	
            text = self.request.get('text')
            if not text.strip():
            	self.send_json_response(False, message = "O texto não pode ser vazio")
            else:
	            bug = BugIssue(author = users.GetCurrentUser(), text = text)
    	        bug.put()
    	        self.send_json_response(True)
    	elif action == "update":
    		if not users.is_current_user_admin():
    			self.error(403)
    		else:
	    		bugID = self.request.get('key')
    			solution = self.request.get("solution")
    			bug = BugIssue.get_by_id(long(bugID))
    			if bug:
    				bug.solution = solution
    				bug.put()
    			else:
    				self.error(404)
    	elif action == "delete":
    		bugID = self.request.get('key')    		
    		if users.is_current_user_admin():
    			bug = BugIssue.get_by_id(long(bugID))
    			if bug:
    				bug.delete()
    			else:
    				self.error(404)
    		else:
    			self.error(403)
        else:
            self.error(404)

class NotFoundPageHandler(BaseRequestHandler):
    def get(self):
        self.error(404)
        self.generate("404.html")

application = webapp.WSGIApplication(
                                     [('/', MainPage),
                                      ('/horario', Horarios),
                                      ('/admin', Admin),
                                      ('/bug_tracker', BugTracker),
                                      ('/.*', NotFoundPageHandler),
                                     ],
                                     debug=_DEBUG)
#if users.is_current_user_admin():
#application = FirePythonWSGI(application)
#wsgiref.handlers.CGIHandler().run(application)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
