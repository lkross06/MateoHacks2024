import redis
import sqlite3
from .models import Account, Profile
import hashlib
import random
import uuid
import os
import shutil

#literals
__REDIS_PORT = 6379
__DATABASE_FILE_NAME = "lab4.db"
__ASCII_NUM_START = 48 #used for generated random alphanumeric symbols
__ASCII_NUM_END = 57
__ASCII_ALPHA_START = 97
__ASCII_ALPHA_END = 122
__SALT_LENGTH = 10 #10 random characters

__sqlite3_conn = sqlite3.connect(__DATABASE_FILE_NAME, check_same_thread=False)
__redis_server = redis.Redis(host="localhost", port=__REDIS_PORT, decode_responses=True) #username : token

#create the sqlite3 tables
cur = __sqlite3_conn.cursor()

cur.execute("create table if not exists accounts (username text not null, password text not null, salt varchar(10) not null);")
cur.execute("create table if not exists profiles (userid integer primary key, fname text, lname text, avatar text, files text);")

__sqlite3_conn.commit()
cur.close()

def __password_encode(salt:str, password:str) -> str:
    salted_pass = salt + password
    return hashlib.sha256(salted_pass.encode()).hexdigest() #sha256 encoding

def __generate_salt() -> str:
    #0-9 + a-z (dont want it to mess up table)
    alphanum = [chr(x) for x in range(__ASCII_NUM_START, __ASCII_NUM_END+1)] + [chr(x) for x in range(__ASCII_ALPHA_START, __ASCII_ALPHA_END+1)]
    salt = "".join([random.choice(alphanum) for x in range(__SALT_LENGTH)])
    return salt

'''
creates an account (login credentials for authentication), uploads it to the sqlite3 accounts table

:param username: username of account
:param password: password of account

:return: Profile object containing an empty profile linked to the account info
'''
def account_create(username:str, password:str) -> Profile:
    #create account

    salt = __generate_salt()

    acc = Account()
    acc.username = username
    acc.password = password
    acc.salt = salt

    #create profile
    prof = Profile()
    prof.username = username

    #create file path
    parent_dir = os.getcwd() #get current working directory (os needs full file path)
    new_path = os.path.join("static/files", username, "")
    files_path = os.path.join(parent_dir, new_path)
    prof.files = new_path

    if not(os.path.exists(files_path)):
        os.mkdir(files_path) #make the directory

    #upload to server
    cur = __sqlite3_conn.cursor()
    cur.execute(f'insert into accounts (username, password, salt) values ("{username}", "{__password_encode(salt, password)}", "{salt}")')
    
    cur.execute(f'select rowid from accounts where username = "{username}";')
    uid = cur.fetchall()[0][0]
    
    cur.execute(f'insert into profiles (userid, files) values ("{uid}", "{files_path}")')
    
    __sqlite3_conn.commit()
    cur.close()

    return prof

'''
authenticates whether the account credentials match with any on the sqlite3 accounts table

:param username: username to check
:param password: password to check

:return: true if account exists and credentials are correct, false otherwise
'''
def account_auth(username:str, password:str) -> bool:
    #get the hash from the database
    cur = __sqlite3_conn.cursor()
    cur.execute(f'select password, salt from accounts where username = "{username}";')

    fetched_results = cur.fetchall()
    if len(fetched_results) > 0:
        phash, psalt = fetched_results[0]
    else:
        return False

    cur.close()

    return phash == __password_encode(psalt, password)

'''
updates account with new re-hashed password using same salt

:param username: username of account to update
:param password: new password for account

:return: true if successful, false otherwise
'''
def account_update_password(username:str, password:str) -> bool:
    #get the salt (can i use the same salt? it shouldn't matter right..)
    cur = __sqlite3_conn.cursor()
    cur.execute(f'select salt from accounts where username = "{username}";')

    salt = cur.fetchall()[0][0]
    new_pass = __password_encode(salt, password)
    cur.execute(f'update accounts set password = "{new_pass}" where username = "{username}";')

    __sqlite3_conn.commit()
    cur.close()

    return True

'''
updates profile information on sqlite3 server

:param username: username of profile to update
:param fname: new first name
:param lname: new last name
:param avatar: bytes encoding an image for new avatar 

:return: true if successful, false otherwise
'''
def profile_update(username:str, fname:str = None, lname:str = None, avatar:str = None) -> bool:
    cur = __sqlite3_conn.cursor()

    cur.execute(f'select rowid from accounts where username = "{username}";')
    uid = cur.fetchall()[0][0]
    
    if fname != None:
        cur.execute(f'update profiles set fname = "{fname}" where userid = {uid};')
    if lname != None:
        cur.execute(f'update profiles set lname = "{lname}" where userid = {uid};')
    if avatar != None:
        cur.execute(f'update profiles set avatar = "{avatar}" where userid = {uid};')
    
    __sqlite3_conn.commit()
    cur.close()

    return True

'''
deletes a profile and the corresponding account information

:param username: username of account/profile to delete

:return: true if successful, false otherwise
'''
def profile_delete(username:str) -> bool:
    cur = __sqlite3_conn.cursor()
    
    cur.execute(f'select rowid from accounts where username = "{username}";')
    uid = cur.fetchall()[0][0]

    #get the avatar and file rel path to delete
    cur.execute(f'select avatar, files from profiles where userid = "{uid}"')
    avatar, files = cur.fetchall()[0]

    print(avatar, files)
    

    cur.execute(f'delete from accounts where username = "{username}";')
    cur.execute(f'delete from profiles where userid = "{uid}";')

    __sqlite3_conn.commit()
    cur.close()

    #remove the avatar and directory of files (plus its contents)
    if os.path.exists(avatar):
        avatar = os.path.join(os.getcwd(), avatar)
        os.remove(avatar)
    if os.path.exists(files):
        shutil.rmtree(files)

    return True

'''
gets the profile given the username

:param username: username of profile to get

:return: Profile object containing all profile info, or None if profile doesnt exist
'''
def profile_get(username:str) -> Profile:
    #TODO: use redis for this. i dont think this function should exist

    cur = __sqlite3_conn.cursor()
    cur.execute(f'select profiles.fname, profiles.lname, profiles.avatar, profiles.files from accounts inner join profiles on accounts.rowid = profiles.userid where accounts.username = "{username}";')
    
    fetched_results = cur.fetchall()

    if len(fetched_results) > 0:
        fname, lname, avatar, files = fetched_results[0]
    else:
        return None

    prof = Profile()
    prof.username = username
    prof.fname = fname
    prof.lname = lname
    prof.avatar = avatar
    prof.files = files

    return prof

'''
creates a token-username pair using the redis server

:param username: username to create a token for

:return: uuidv4 token
'''
def token_create(username:str) -> str:
    token = uuid.uuid4().hex
    __redis_server.set(username, token)

    return token

'''
deletes a token-username pair using the redis server

:param username: username to delete the token of

:return: true if successful, false otherwise
'''
def token_delete(username:str) -> bool:
    __redis_server.delete(username)
    return True

'''
gets a token-username pair using the redis server

:param username: username to get the token of

:return: uuidv4 token
'''
def token_get(username:str) -> str:
    return __redis_server.get(username)