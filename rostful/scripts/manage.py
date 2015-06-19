# All ways to run rostful and all Manager commands
# should be defined here for consistency
from __future__ import absolute_import
import os
import sys

import rostful

import logging
from logging.handlers import RotatingFileHandler

from flask_migrate import Migrate, MigrateCommand
from flask_script import Manager, Option

#setup migrations
#python flask.py db migrate
#python flask.py db upgrade
# Need help ?
#python flask.py db --help

migrate = Migrate(rostful.rostful_server.app, rostful.rostful_server.db)
manager = Manager(rostful.rostful_server.app)
#TODO : http://stackoverflow.com/questions/29872867/using-flask-migrate-with-flask-script-and-application-factory/29882346#29882346
#manager.add_option("-c", "--config", dest="config_module", required=False)
manager.add_command('db', MigrateCommand)

#TODO : flexible config by command line param ???

@manager.command
def init():
    """
    Create useful configuration files and database on first install
    """
    #Create instance config file name, to make it easy to modify when deploying
    filename = os.path.join(rostful.rostful_server.app.instance_path, 'flask_config.py')
    if not os.path.isfile(filename) :
        #this will create the directories if needed
        try:
            os.makedirs(os.path.dirname(filename))
        except OSError as exception: #preventing race condition just in case
            if exception.errno != errno.EEXIST:
                raise
        #this will create the file
        rostful.rostful_server.app.open_instance_resource('flask_config.py', 'w')

    #run db upgrade to make sure our db schema is initialized ( here instead of in shell script )
    #TODO
    #add seed data to the database
    #TODO : prompt
    #prompt_bool(name, default=False, yes_choices=None, no_choices=None)
    rostful.rostful_server.user_datastore.create_user(email='admin@yujin.net', password='adminpass')
    rostful.rostful_server.db.session.commit()


from flask_script import Command

@manager.command
@manager.option('-h', '--host', dest='host', default='')
@manager.option('-p', '--port', type=int, dest='port', default=8080)
@manager.option('-r', '--ros_args', dest='ros_args', default='')
def flask(host='', port=8080, ros_args=''):
    try:
        #type=int doesnt see to work
        if isinstance(port, basestring) : port = int(port)

        rostful.rostful_server.app.logger.info('host %r', host)
        rostful.rostful_server.app.logger.info('port %r', port)
        rostful.rostful_server.app.logger.info('ros_args %r', ros_args)

        #Disable this line to debug the webapp without ROS
        rostful.rostful_server.launch(ros_args.split())

        #Adding a logger
        if not rostful.rostful_server.app.debug:
            file_handler = RotatingFileHandler('rostful.log', maxBytes=10000, backupCount=1)
            file_handler.setLevel(logging.INFO)
            rostful.rostful_server.app.logger.addHandler(file_handler)

        rostful.rostful_server.app.logger.info('Starting Flask server on port %d', port)
        # debug is needed to investigate server errors.
        # use_reloader set to False => killing the ros node also kills the server child.
        rostful.rostful_server.app.run(host=host, port=port, debug=True, use_reloader=False)
        # TODO : move this to rostful_server launch method

    except KeyboardInterrupt:
        rostful.rostful_server.app.logger.info('Shutting down the Flask server')
        rostful.rostful_server.shutdown()


### TODO : This can be simplified when moving to gunicorn >= 19
from gunicorn.app.base import Application

class GunicornServer(Command):

    description = 'Run the app within Gunicorn'

    def __init__(self, host='127.0.0.1', port=8000, workers=6):

        self.port = port
        self.host = host
        self.workers = workers

    def get_options(self):
        return (
            Option('-h', '--host',
                   dest='host',
                   default=self.host),

            Option('-p', '--port',
                   dest='port',
                   type=int,
                   default=self.port),

            Option('-w', '--workers',
                   dest='workers',
                   type=int,
                   default=self.workers),
        )

    def handle(self, app, *args, **kwargs):

        host = kwargs['host']
        port = kwargs['port']
        workers = kwargs['workers']

        def remove_non_gunicorn_command_line_args():
            import sys
            args_to_remove = ['--port','-p']
            def args_filter(name_or_value):
                keep = not args_to_remove.count(name_or_value)
                if keep:
                    previous = sys.argv[sys.argv.index(name_or_value) - 1]
                    keep = not args_to_remove.count(previous)
                return keep
            sys.argv = filter(args_filter, sys.argv)

        remove_non_gunicorn_command_line_args()

        from gunicorn import version_info
        if version_info < (0, 9, 0):
            from gunicorn.arbiter import Arbiter
            from gunicorn.config import Config
            arbiter = Arbiter(Config({'bind': "%s:%d" % (host, int(port)),'workers': workers}), app)
            arbiter.run()
        else:
            class FlaskApplication(Application):
                def init(self, parser, opts, args):
                    return {
                        'bind': '{0}:{1}'.format(host, port),
                        'workers': workers
                    }

                def load(self):
                    return app

            FlaskApplication().run()

manager.add_command('gunicorn', GunicornServer())



import logging
import click

#TODO : handle config file via command line arg ?
@manager.command
@manager.option('-r', '--ros_args', dest='ros_args', default='', help='holder for all ros arguments if needed')
def worker(ros_args):
    #click.echo('ros_args=%s' % ros_args)
    try:
        logging.basicConfig(level=logging.INFO)

        logging.debug('Starting Celery worker')
        # Starting Celery worker process
        rostful.rostful_worker.launch(ros_args)

    except KeyboardInterrupt:
        logging.debug('Shutting down the Celery worker')


#to be able to use Flask-Script directly on this package
manager.run()