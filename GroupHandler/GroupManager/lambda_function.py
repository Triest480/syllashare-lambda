import pymysql
import json
import os
import uuid
import time

def getUser(cursor, userID):
    cursor.execute("""SELECT u.id AS id, u.username AS username, u.first_name AS firstName, u.last_name AS lastName, u.pic_key AS picKey, 
        s.name AS schoolName, s.city AS schoolCity, s.state AS schoolState, s.pic_key AS schoolPicKey
        FROM user_data_user u LEFT JOIN user_data_school s ON u.school_id=s.name
        WHERE u.id=%s""", (userID))
    for (userID, username, firstName, lastName, picKey, schoolName, schoolCity, schoolState, schoolPicKey) in cursor:
        schoolDict = None
        if (schoolName is not None):
            schoolDict = {
                "name": schoolName,
                "city": schoolCity,
                "state": schoolState,
                "picKey": schoolPicKey
            }
        return { "id": userID, "username": username, "firstName": firstName, "lastName": lastName, "picKey": picKey, "school": schoolDict }
    return None
    
    
def isInGroup(cursor, groupName, userID):
    return (cursor.execute('SELECT groupName FROM GroupsToUsers WHERE groupName=%s AND userID=%s AND accepted=1', (groupName, userID)) > 0)
    
    
def createGroup(connection, cursor, groupName, groupPrivate, userID):
    if cursor.execute('INSERT INTO Groups VALUES (%s, %s)', (groupName, str(1 if groupPrivate else 0))) > 0:
        if cursor.execute('INSERT INTO GroupsToUsers VALUES (%s, %s, %s)', (groupName, userID, str(1))) > 0:
            connection.commit()
            return { "name": groupName, "private": groupPrivate }
        return { "errMsg": "Failed to add user into group" }
    return { "errMsg": "Failed to create group" }
    
    
def joinGroup(connection, cursor, groupName, userID):
    if cursor.execute('SELECT private FROM Groups WHERE name=%s', (groupName)) > 0:
        groupPrivate = cursor.fetchone()[0]
        if groupPrivate:
            if cursor.execute('UPDATE GroupsToUsers SET accepted=%s WHERE groupName=%s AND userID=%s', (str(1), groupName, userID)) <= 0:
                return { "errMsg": "User not invited" }
        else:
            cursor.execute('INSERT INTO GroupsToUsers VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE accepted=%s', (groupName, groupPrivate, str(1), str(1)))
        connection.commit()
        group = getGroup(connection, cursor, groupName, userID)["group"]
        return { "group": group, "user": getUser(cursor, userID), "userID": userID, "groupName": groupName }
    return { "errMsg": "Group not found" }


def leaveGroup(connection, cursor, groupName, userID):
    group = getGroup(connection, cursor, groupName, userID)["group"]
    if cursor.execute('DELETE FROM GroupsToUsers WHERE groupName=%s AND userID=%s', (groupName, userID)) > 0:
        connection.commit()
        return { "group": group, "user": getUser(cursor, userID), "userID": userID, "groupName": groupName }
    print("User not in or not invited to group")
    return { "errMsg": "Not in or have not been invited to group" }
    
    
def inviteToGroup(connection, cursor, groupName, inviteToUserID, invokerUserID):
    if isInGroup(cursor, groupName, invokerUserID):
        if cursor.execute('INSERT INTO GroupsToUsers VALUES (%s, %s, %s)', (groupName, inviteToUserID, str(0))) > 0:
            connection.commit()
            group = getGroup(connection, cursor, groupName, invokerUserID)["group"]
            print("GROUP: ", group)
            return { "group": group, "user": getUser(cursor, inviteToUserID), "userID": inviteToUserID, "groupName": groupName }
        return { "errMsg": "Failed to invite user" }
    return { "errMsg": "You can't invite someone to a group you're not in" }
    
    
def createChat(connection, cursor, groupName, chatName, chatSubject, userID):
    if isInGroup(cursor, groupName, userID):
        chatID = uuid.uuid4()
        if cursor.execute('INSERT INTO Chats VALUES (%s, %s, %s, %s)', (str(chatID), groupName, chatName, chatSubject)) > 0:
            connection.commit()
            return { "id": str(chatID), "name": chatName, "subject": chatSubject, "groupName": groupName }
        return { "errMsg": "Could not create group" }
    return { "errMsg": "User is not in group" }
  
    
def createMessage(connection, cursor, chatID, text, objKey, creationEpochSecs, userID):
    #Check if user is part of group that the chat belongs to
    print("Creating msg")
    if cursor.execute("""SELECT c.id FROM Chats c 
        INNER JOIN GroupsToUsers gu ON c.groupName=gu.groupName 
        WHERE c.id=%s AND gu.userID=%s AND gu.accepted=%s""", (chatID, userID, str(1))) > 0:
            print("SELECT DONE")
            msgID = uuid.uuid4()
            if cursor.execute("""INSERT INTO Messages VALUES (%s, %s, %s, %s, %s, %s)""", (str(msgID), chatID, text, objKey, str(creationEpochSecs), userID)) > 0:
                print("MSG Inserted")
                connection.commit()
                print("MSG COMMIT")
                msg = { "id": str(msgID), "text": text, "objKey": objKey, "creationEpochSecs": creationEpochSecs, "chatID": chatID, "senderID": userID }
                return { "message": msg, "sender": getUser(cursor, userID), "chatID": chatID }
            return { "errMsg": "Could not add message" }
    return { "errMsg": "User not in group" }


    
def getGroups(connection, cursor, userID):
    cursor.execute("""SELECT g.name, g.private FROM GroupsToUsers gu INNER JOIN Groups g ON gu.groupName=g.name WHERE gu.userID=%s""", (userID))
    groups = []
    for (groupName, groupPrivate) in cursor:
        groups.append({ "group": { "name": groupName, "private": groupPrivate } })
    for group in groups:
        groupContents = getGroup(connection, cursor, group["group"]["name"], userID)
        group["group"]["users"] = groupContents["group"]["users"]
        group["group"]["chats"] = groupContents["group"]["chats"]
        group["accepted"] = groupContents["accepted"]
    return groups
            

def getGroup(connection, cursor, groupName, userID):
    if cursor.execute("""SELECT g.private, gu.accepted FROM GroupsToUsers gu INNER JOIN Groups g ON gu.groupName=g.name WHERE gu.userID=%s AND gu.groupName=%s""", (userID, groupName)) > 0:
        row = cursor.fetchone()
        groupPrivate = row[0]
        groupAccepted = row[1]
        group = {
            "name": groupName,
            "private": groupPrivate,
            "users": [],
            "chats": []
        }
        cursor.execute("""SELECT gu.userID, gu.accepted FROM GroupsToUsers gu WHERE gu.groupName=%s""", (groupName))
        userQueryRes = cursor.fetchall()
        for (userID, accepted) in userQueryRes:
            print("USERID: ", userID)
            user = getUser(cursor, userID)
            print("USER: ", user)
            user["accepted"] = accepted
            group["users"].append(user)
        cursor.execute("""SELECT c.id, c.name, c.subject FROM Chats c WHERE c.groupName=%s""", (groupName))
        for (chatID, chatName, chatSubject) in cursor:
            group["chats"].append({ "id": chatID, "name": chatName, "subject": chatSubject })
        return { "accepted": groupAccepted, "group": group }
    print("Group: ", groupName, " with member ", userID, " does not exist")
    return { "errMsg": "User not a member of group or group does not exist" }


def getMessages(connection, cursor, chatID, userID):
    print("GET MSG CHAT ID: ", chatID)
    if cursor.execute("""SELECT c.id FROM Chats c 
        INNER JOIN GroupsToUsers gu ON c.groupName=gu.groupName 
        WHERE c.id=%s AND gu.userID=%s AND gu.accepted=%s""", (chatID, userID, 1)) > 0:
            print("Messages success")
            senderIDs = {}
            messages = []
            cursor.execute("""SELECT id, text, objKey, creationEpochSecs, senderID FROM Messages WHERE chatID=%s ORDER BY creationEpochSecs DESC""", (chatID))
            print("Message loop")
            for (id, text, objKey, creationEpochSecs, senderID) in cursor:
                print("Message: ", id)
                senderIDs[senderID] = True
                messages.append({ "id": id, "text": text, "objKey": objKey, "creationEpochSecs": creationEpochSecs, "chatID": chatID, "senderID": senderID })
            print("Senders loop")
            senders = []
            for senderID in senderIDs:
                print("Sender: ", senderID)
                senders.append(getUser(cursor, senderID))
            print("MS: ", messages, " SS", senders)
            return { "messages": messages, "senders": senders }
    return { "errMsg": "User not in group" }
    
    
def searchGroups(connection, cursor, query, userID):
    resp = []
    if cursor.execute("""SELECT g.name, g.private FROM Groups g
        WHERE LCASE(g.name) LIKE %s ORDER BY LENGTH(g.name), g.name LIMIT 50""", (query + '%')) > 0:
            for (name, private) in cursor:
                resp.append({"name": name, "private": private})
    return resp
    
def handler(event, context):
    dbHost = os.environ['db_host']
    dbUser = os.environ['db_user']
    dbPwd = os.environ['db_pwd']
    dbDb = os.environ['db_db']
        
    connection = pymysql.connect(user=dbUser, password=dbPwd,
                        host=dbHost,
                        database=dbDb)
    cursor = connection.cursor()
    
    userID = event["cognitoIdentityId"]
    
    print(event)
    args = event["arguments"]
    #python has no switch-case
    if (event["type"] == "CreateGroup"):
        return createGroup(connection, cursor, args["groupName"], args["groupPrivate"], userID)
    elif (event["type"] == "JoinGroup"):
        return joinGroup(connection, cursor, args["groupName"], userID)
    elif (event["type"] == "LeaveGroup"):
        return leaveGroup(connection, cursor, args["groupName"], userID)
    elif (event["type"] == "InviteToGroup"):
        return inviteToGroup(connection, cursor, args["groupName"], args["inviteToUserID"], userID)
    elif (event["type"] == "CreateChat"):
        return createChat(connection, cursor, args["groupName"], args["chatName"], args["chatSubject"], userID)
    elif (event["type"] == "CreateMessage"):
        return createMessage(connection, cursor, args["chatID"], args["text"], args["objKey"], args["creationEpochSecs"], userID)
    elif (event["type"] == "GetGroups"):
        return getGroups(connection, cursor, userID)
    elif (event["type"] == "GetGroup"):
        return getGroup(connection, cursor, args["groupName"], userID)
    elif (event["type"] == "GetMessages"):
        return getMessages(connection, cursor, args["chatID"], userID)
    elif (event["type"] == "SearchGroups"):
        return searchGroups(connection, cursor, args["query"], userID)
    return { "errMsg": "Event not found" }