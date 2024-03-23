from flask import Flask, redirect, send_file, request, render_template, make_response
from db_manager import *
import os

logged_in = {} #token:profile

'''
gets the correct error message to display based on error type

:param type: type of error (shorthand for message)

:return: error message
'''
def error_message_get(type:int) -> str:
    if type == 1:
        return "incorrect username or password"
    elif type == 2:
        return "username already exists"
    elif type == 3:
        return "invalid request"
    elif type == 4:
        return "profile does not exist"
    
    return "please try again"


app = Flask(__name__)

@app.route("/")
def home():
    token = request.cookies.get("token")
    prof = logged_in.get(token)
    if token == None: #not logged in
        return redirect("/login")
    if prof == None: #previous token exists but not logged in
        resp = make_response(redirect("/login"))
        resp.set_cookie(token, "", max_age=0)
        return resp
    
    user = prof.username
    return redirect(f"/{user}/profile")

@app.route("/login", methods=["POST", "GET"])
def login():

    if request.method == "POST":
        mode = request.form.get("mode")
        username = request.form.get("username")
        password = request.form.get("password")
        if mode == "login":
            if account_auth(username, password): #check the database for correct account info
                prof = profile_get(username)

                response = make_response(redirect(f"/{username}/profile"))
                token = token_create(username) #create a session token
                response.set_cookie(key="token", value=token)

                logged_in[token] = prof #add profile to logged in profiles

                return response
            else:
                return render_template("login.html", error_message=error_message_get(1)) #invalid login
        elif mode == "register":
            if profile_get(username) != None: #check to see if account with that username exists
                return render_template("login.html", error_message=error_message_get(2)) #username already exists
            
            #create account
            prof = account_create(username, password)

            response = make_response(redirect(f"/{username}/profile"))
            token = token_create(username)
            response.set_cookie(key="token", value=token)

            logged_in[token] = prof

            return response
        
        else:
            return "FAILURE" #if they mess with html then "swear your butt off" -fern
    else:
        return render_template("login.html", error_message=None)
    
@app.route("/logout", methods=["POST"])
def logout():
    token = request.cookies.get("token")

    profile = logged_in[token]
    token_delete(profile.username) #remove from redis server

    logged_in[token] = None #remove from logged in profiles

    response = make_response(redirect("/"))
    response.set_cookie("token", "", max_age=0) #delete cookie

    return response

@app.route("/<user>/profile", methods=["POST", "GET"])
def user_profile(user):
    #print the cookie and username
    token = request.cookies.get("token")
    is_logged_in = token != None
    if is_logged_in:
        profile = logged_in.get(token)
        if profile == None: #token exists but is invalid
            return redirect("/")
    else:
        profile = profile_get(user)
        if profile == None: #profile does not exist
            return render_template("login.html", error_message=error_message_get(4))

    if request.method == "GET":
        #make sure the user is logged in AND its their profile
        is_personal_account = token == token_get(user) and is_logged_in
        return render_template("profile.html", profile=profile.jsonify(), show_options=is_personal_account)
    else:
        if not(is_logged_in):
            return render_template("login.html", error_message=error_message_get(3))
        
        action = request.form.get("action")

        if action == "password":
            password = request.form.get("password")
            account_update_password(user, password) #server side only
        elif action == "picture":
            picture = request.files["picture"]

            ext = picture.filename.split(".")[1] #get file type (i.e. png, jpg, etc.)
            new_loc = os.path.join("static/avatars", "".join([user, ".", ext]))

            picture.save(new_loc) #save locally

            profile_update(username=user, avatar=new_loc)
            logged_in[token].avatar = new_loc

        elif action == "name":
            fname = request.form.get("fname")
            lname = request.form.get("lname")
            logged_in[token].fname = fname
            logged_in[token].lname = lname
            profile_update(username=user, fname=fname, lname=lname)
        elif action == "delete":
            confirmation = request.form.get("confirmation")
            if confirmation == user:
                #invalidate tokens and delete the profile
                profile_delete(user)
                token_delete(user)
            
                token = request.cookies.get("token")
                logged_in[token] = None

                response = make_response(redirect("/login"))
                response.set_cookie("token", "", max_age=0) #delete cookie

                return redirect("/")
            
        return render_template("profile.html", profile=profile.jsonify(), show_options=True)

@app.route("/<user>/files", methods=["POST"])
def user_files(user):
    token = request.cookies.get("token")

    if token != None:
        file = request.files["file"]
                
        full_path = logged_in[token].files
        file.save(os.path.join(full_path, file.filename)) #save locally

        return "SUCCESS"
    else:
        return redirect(f"/{user}/profile")

if __name__ == "__main__":
    app.run(port=8022)