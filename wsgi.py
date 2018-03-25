from app import app

if __name__ == "__main__":
    # initialize the log handler
    log_handler = RotatingFileHandler(config.get('app', 'logpath', 0), maxBytes=10000, backupCount=1)
    
    # set the log handler level
    log_handler.setLevel(logging.INFO)

    # set the app logger level
    app.logger.setLevel(logging.INFO)

    app.logger.addHandler(log_handler)    
    app.run()
