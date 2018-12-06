var AWS = require('aws-sdk');
var s3 = new AWS.S3();
const vision = require('@google-cloud/vision');

var mysql = require('mysql');
const ImageDataURI = require('image-data-uri');

var connection = mysql.createConnection({
	host: process.env.db_host,
	user: process.env.db_user,
	password: process.env.db_pwd,
	database: process.env.db_db
});

const client = new vision.ImageAnnotatorClient({
	keyFile: '/var/task/tryst.json'
});

exports.handler = function(event, context, callback) {
    context.callbackWaitsForEmptyEventLoop = false;
    var userID = event.requestContext.identity["cognitoIdentityId"];
    var imgUrlEncoded = JSON.parse(event.body).img;
    var imgDecoded = ImageDataURI.decode(imgUrlEncoded);
    var imgBuffer = imgDecoded["dataBuffer"];
    var imgType = imgDecoded["imageType"];
    var slashIdx = imgType.indexOf('/');
    imgType = imgType.substr(slashIdx + 1);
	client
	    .safeSearchDetection(imgBuffer)
	    .then((results) => {
	    	console.log("Safe search results: ", results);
	        var annotations = results[0].safeSearchAnnotation;
	        if ((annotations.adult == "UNLIKELY" || annotations.adult == "VERY_UNLIKELY")
	            && (annotations.medical == "UNLIKELY" || annotations.medical == "VERY_UNLIKELY")
	            && (annotations.violence == "UNLIKELY" || annotations.violence == "VERY_UNLIKELY")
	            && (annotations.racy == "UNLIKELY" || annotations.racy == "VERY_UNLIKELY")) {
	                var newKey = `public/profileImgs/${userID}.${imgType}`;
	                s3.upload({
	                  Bucket: 'syllasharedata',
	                  Key: newKey,
	                  Body: imgBuffer
	                })
	                .promise()
	                .then(() => {
	                    connection.query('UPDATE user_data_user SET pic_key=? WHERE id=?', [newKey, userID], (function (err) {
	                        if (err) {
	                            console.error("Error inserting into database");
	                            callback(null, { statusCode: 500, headers: {
						                "Access-Control-Allow-Origin" : "*",
						                "Access-Control-Allow-Credentials" : true
            						}, body: JSON.stringify({ "message": "Database update failed" }) });
	                            return;
	                        }
	                        console.log("Success!");
	                        callback(null, { statusCode: 200, headers: {
					                "Access-Control-Allow-Origin" : "*",
					                "Access-Control-Allow-Credentials" : true
            					}, body: JSON.stringify({ "picKey": newKey }) });
	                    }));
	                })
	                .catch((err) => {
	                	console.error("Failed S3 upload: ", err);
	                    callback(null, { statusCode: 500, headers: {
				                "Access-Control-Allow-Origin" : "*",
				                "Access-Control-Allow-Credentials" : true
            				}, body: JSON.stringify({ "message": "Error uploading image to S3: " + err }) });
	                });
                }
                else {
                    callback(null, { statusCode: 400, headers: {
			                "Access-Control-Allow-Origin" : "*",
			                "Access-Control-Allow-Credentials" : true
            			}, body: JSON.stringify({ "message": "Inappropiate profile pic" }) });
                }
	        })
	        .catch(err => {
	            console.error("SafeSearchFail: ", err);
	            callback(null, { statusCode: 500, headers: {
		                "Access-Control-Allow-Origin" : "*",
		                "Access-Control-Allow-Credentials" : true
            		}, body: JSON.stringify({ "message": "Safe search failed" }) });
	        });
};