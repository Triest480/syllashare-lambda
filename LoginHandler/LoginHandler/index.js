var mysql = require('mysql');
var hat = require('hat');
var moment = require('moment');

var TOKEN_DURATION_MINS = process.env.token_mins;

var connection = mysql.createConnection({
	host: process.env.db_host,
	user: process.env.db_user,
	password: process.env.db_pwd,
	database: process.env.db_db
});

exports.handler = (event, context, callback) => {
    context.callbackWaitsForEmptyEventLoop = false;
    
    var userID = event.requestContext.identity["cognitoIdentityId"];
    //TODO: Include username in request
    var givenName = null;
    
    var genUsername = () => {
        return new Promise((resolve, reject) => {
            connection.query("SELECT id, count FROM UserCounts ORDER BY count ASC LIMIT 1 FOR UPDATE", [], (err, data) => {
                if (err) {
                    reject(err);
                    return;
                }
                var username = data[0].id + data[0].count.toString();
                connection.query("UPDATE UserCounts SET count=? WHERE id=?", [data[0].count + 1, data[0].id], (err) => {
                    if (err) {
                        reject(err);
                        return;
                    }
                    connection.commit((err) => {
                        if (err) {
                            reject(err);
                            return;
                        }
                        console.log("Generated username: ", username);
                        resolve(username);
                    });
                });
            });
        });
    };
    
    var createUser = (name, cognitoID) => {
        return new Promise((resolve, reject) => {
            connection.query("INSERT INTO user_data_user (id, username) VALUES (?, ?)", [cognitoID, name], (err) => {
                if (err) {
                    reject(err);
                    return;
                }
                resolve();
            });
        });
    };
    
    var initUser = (userID, name = null) => {
        return new Promise((resolve, reject) => {
            connection.query('SELECT * FROM user_data_user WHERE id=?', [userID], (err, results) => {
                if (err) {
                    reject(err);
                    return;
                }
                if (results.length == 0) {
                    var namePromise = null;
                    if (name == null) {
                        namePromise = genUsername();
                    } else {
                        namePromise = new Promise((resolve) => {
                            resolve(name);
                        });
                    }
                    namePromise.then((name) => {
                        createUser(name, userID).then(() => {
                            resolve();
                        });
                    }).catch((err) => {
                        reject(err);
                    });
                } else {
                    resolve();
                }
            });
        });
    };
    
    var getActiveToken = (userID) => {
        return new Promise((resolve, reject) => {
            connection.query('SELECT syllashare_token, expiration_date AS expDate FROM syllatokens_syllasharetoken WHERE expiration_date >= NOW() AND user_id=?', [userID], (err, data) => {
                if (err) {
                    reject(err);
                    return;
                }
                if (data.length == 0) {
                    resolve(null, null);
                    return;
                }
                resolve(data[0].token, moment.utc(data[0].expDate).unix());
            });
        });
    };
    
    var addToken = (userID) => {
        return new Promise((resolve, reject) => {
            var token = hat();
            var expMoment = moment().utc().add(TOKEN_DURATION_MINS, 'm');
            var expStr = expMoment.format("YYYY-MM-DD HH:mm:ss");
            connection.query('INSERT INTO syllatokens_syllasharetoken (syllashare_token, user_id, expiration_date) VALUES ? ON DUPLICATE KEY UPDATE syllashare_token=?, expiration_date=?', [[[token, userID, expStr]], token, expStr], (err, results) => {
                if (err) {
                    reject(err);
                    return;
                }
                resolve(token, expMoment.unix());
            });
        });
    };
    
    var run = (userID, name = null) => {
        return new Promise((resolve, reject) => {
            //Get existing token
            getActiveToken(userID).then((token, expEpochMillis) => {
                if (token != null) {
                    resolve(token, expEpochMillis);
                    return;
                }
                //Check if the user is initialized. if not, initialize
                initUser(userID, name).then(() => {
                    //Add token to the database
                    addToken(userID).then((token, expEpochMillis) => {
                        resolve(token, expEpochMillis);
                    }).catch((err) => {
                        reject(err);
                    });
                }).catch((err) => {
                    reject(err);
                });
            }).catch((err) => {
                reject(err);
            });
        });
    };
    
    run(userID, givenName).then((token, expEpochMillis) => {
        callback(null, {
            statusCode: 200,
            headers: {
                "Access-Control-Allow-Origin" : "*",
                "Access-Control-Allow-Credentials" : true
            }, 
            body: JSON.stringify({ "userID": userID, "token": token, "expEpochMillis": expEpochMillis })
        });
    })
    .catch((err) => {
        console.error("ERROR: ", err.message);
        callback(null, {
            statusCode: 400,
            headers: {
                "Access-Control-Allow-Origin" : "*",
                "Access-Control-Allow-Credentials" : true
            }, 
            body: JSON.stringify({ "msg": err.message }) 
        });
    });
};