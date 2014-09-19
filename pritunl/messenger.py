from pritunl.constants import *
from pritunl.exceptions import *
from pritunl.descriptors import *
import pritunl.mongo as mongo
import pymongo
import time
import datetime
import bson

class Messenger(object):
    @cached_static_property
    def collection(cls):
        return mongo.get_collection('messages')

    def publish(self, channels, message, transaction=None):
        doc = {
            'timestamp': datetime.datetime.utcnow(),
            'message': message,
        }

        if transaction:
            tran_collection = transaction.collection(
                self.collection.collection_name)

            if isinstance(channels, str):
                doc['channel'] = channels
                tran_collection.update({
                    '_id': bson.ObjectId(),
                }, doc, upsert=True)
            else:
                for channel in channels:
                    doc_copy = doc.copy()
                    doc_copy['channel'] = channel

                    tran_collection.bulk().find({
                        '_id': bson.ObjectId(),
                    }).upsert().update(doc_copy)
                tran_collection.bulk_execute()
        else:
            if isinstance(channels, str):
                doc['channel'] = channels
                docs = doc
            else:
                docs = []
                for channel in channels:
                    doc_copy = doc.copy()
                    doc_copy['channel'] = channel
                    docs.append(doc_copy)
            self.collection.insert(docs)

    def get_cursor_id(self, channels):
        spec = {}

        if isinstance(channels, str):
            spec['channel'] = channels
        else:
            spec['channel'] = {'$in': channels}

        try:
            return self.collection.find(spec).sort(
                '$natural', pymongo.DESCENDING)[0]['_id']
        except IndexError:
            pass

    def subscribe(self, channels, cursor_id=None, timeout=None,
            yield_delay=None):
        start_time = time.time()
        cursor_id = cursor_id or self.get_cursor_id(channels)
        while True:
            try:
                spec = {}

                if isinstance(channels, str):
                    spec['channel'] = channels
                else:
                    spec['channel'] = {'$in': channels}

                if cursor_id:
                    spec['_id'] = {'$gt': cursor_id}
                cursor = self.collection.find(spec, tailable=True,
                    await_data=True).sort('$natural', pymongo.ASCENDING)

                while cursor.alive:
                    for doc in cursor:
                        cursor_id = doc['_id']
                        yield doc

                        if yield_delay:
                            time.sleep(yield_delay)

                            spec = {
                                '_id': {'$gt': cursor_id},
                                'channel': channels,
                            }
                            cursor = self.collection.find(spec).sort(
                                '$natural', pymongo.ASCENDING)

                            for doc in cursor:
                                yield doc

                            return
                    if timeout and time.time() - start_time >= timeout:
                        return
            except pymongo.errors.AutoReconnect:
                time.sleep(0.2)
