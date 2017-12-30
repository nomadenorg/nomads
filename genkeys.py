
from hashlib import pbkdf2_hmac
from binascii import hexlify
from os import urandom


pw = b'test'
salt = urandom(32)
alg = 'sha256'
rounds = 100000
name = 'mark'

hashed_pw = pbkdf2_hmac(alg, pw, salt, rounds)

print("{0}:{1}:{2}:{3}:{4}".format(alg, hexlify(salt),
                                   rounds, hexlify(hashed_pw),
                                   name))
