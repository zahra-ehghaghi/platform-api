from flask import Flask, jsonify
import datetime
import socket

app = Flask(__name__)
@app.route('/api/v1/info')
def info():
    return jsonify({
        'hostname': socket.gethostname(),
        'time':  datetime.datetime.now().strftime("%I:%M:%S%p on %B %d, %Y"),
        'message': "Hallo man. Du machst toll ",
        'deployed_on': 'kubernetes' ,
        'env': '${{values.app_env}}' ,
        'app_name': '${{values.app_name}}'

    })


@app.route('/api/v1/healthz')
def healthz():
    return jsonify({'status': 'up' }) , 200

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
