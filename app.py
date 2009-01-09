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
import calendar
import re

import simplejson as json

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

_DEBUG = True

DAY_START = 8

DIAS_SEMANA = ('Domingo', 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado')

GESTOES = set(["Projetos", "Marketing", "Desenvolvimento"])

class Gestao(db.Model):
    nome = db.StringProperty()

class Membro(db.Model):
    user = db.UserProperty()
    nome = db.StringProperty(required = True)
    gestao = db.StringProperty(required = True, verbose_name="Gestão", choices=GESTOES)
    coordenador = db.BooleanProperty(default=False)
    compromissos = db.ListProperty(str)

class MembroForm(djangoforms.ModelForm):
  class Meta:
    model = Membro
    exclude = ['user', 'compromissos']
    
class GestaoForm(djangoforms.ModelForm):
    class Meta:
        model = Gestao

class BaseRequestHandler(webapp.RequestHandler):
    """Supplies a common template generation function.

    When you call generate(), we augment the template variables supplied with
    the current user in the 'user' variable and the current webapp request
    in the 'request' variable.
    """
    def generate(self, template_name, **template_values):

        values = {
            'is_admin': users.is_current_user_admin(),
            'request': self.request,
            'user': users.GetCurrentUser(),
            'login_url': users.CreateLoginURL(self.request.uri),
            'logout_url': users.CreateLogoutURL(self.request.uri),
            'application_name': 'FoG Horarios',
            'membro': self.get_membro_atual(),
            'gestoes': GESTOES,
        }
        values.update(template_values)
        directory = os.path.dirname(__file__)
        path = os.path.join(directory, os.path.join('templates', template_name))
        self.response.out.write(template.render(path, values, debug=_DEBUG))
        
    def get_membro_atual(self):
        membro = Membro.all().filter('user =', users.GetCurrentUser()).get()        
        return membro        

#class EditRequestHandler(webapp.RequestHandler):
    
class MainPage(BaseRequestHandler):
    def get(self):
        action = self.request.get('action')
        membro = Membro.all().filter('user =', users.GetCurrentUser()).get()
        if action == 'getList':
            self.response.out.write(json.dumps(membro.compromissos))
        else:
            if not membro:
                self.generate('escolher_gestao.html', user_form = MembroForm().as_p())
            else:
                self.generate('editar_calendario.html',
                    days_of_week = DIAS_SEMANA,
                    hours = [i / 2 + DAY_START for i in range((24-DAY_START) * 2)],
                )
    
    def post(self):        
        #regexp = re.compile('(\d+)_(\d+)')        
        #day_string, hour_string = regexp.search(self.request.get('id')).groups()
        compromissos = json.loads(self.request.get('list'))
        self.response.out.write(compromissos)
        membro = Membro.all().filter('user =', users.GetCurrentUser()).get()
        membro.compromissos = compromissos
        membro.put()

class Admin(BaseRequestHandler):
    def createForm(self, membro):
        if self.allow_edit(membro):
            return MembroForm(instance = membro).as_p()   
        else:
            return str(membro.user)
        
    def allow_edit(self, membro):
        #return membro
        return users.is_current_user_admin() or (not membro) or membro.user == users.GetCurrentUser()
    
    def get(self):
        #self.get_membro_atual()
        membros = Membro.all()
        self.generate('admin.html',             
            membros = [{'membro': membro,
                        'userid': membro.user.email(),
                        'form': self.createForm(membro),
                        'allow_edit': self.allow_edit(membro),
                       } for membro in membros],
        )
        
    def post(self):
        action = self.request.get('action')
        userID = self.request.get('userID')
        if userID:
            user = users.User(userID)
        else:
            user = users.GetCurrentUser()
        membro = Membro.all().filter('user =', user).get()
        if not self.allow_edit(membro):
            self.response.out.write('Você não pode editar outros usuários')
            return        
        status = None
        if action == 'removeUser':
            if user == users.GetCurrentUser():
                self.response.out.write("Não é possivel remover o usuário atual")
            else:
                membro.delete()
        elif action == 'editarGestao':
            gestaoID = self.request.get('gestaoID')
            if gestaoID:
                gestao = Gestao.get(gestaoID)
            else:
                gestao = None
            form = GestaoForm(data=self.request.POST, instance = gestao)            
            form.save()
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
            #else:
            #    return
            #    self.response.out.write("saved")
            #else:
            #    self.response.out.write("error")
        elif action == 'mudarGestao':
            if not membro:
                membro = Membro()
                membro.user = users.GetCurrentUser()
            membro.gestao = self.request.get('gestao')
            membro.put()
        if status:
            self.response.out.write("<div id=\"status\" style=\"display: none\">%s</div>" % status)            
        redirect = self.request.get('redirect')
        if redirect:
            self.redirect(redirect)

application = webapp.WSGIApplication(
                                     [('/', MainPage),
                                      ('/admin', Admin)],
                                     debug=_DEBUG)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
