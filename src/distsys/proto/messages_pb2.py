"""Runtime Protobuf definitions for Phase 1.

This file mirrors ``proto/messages.proto`` and is intentionally checked in so the
Phase-1 repository works even before ``grpcio-tools`` is installed. Running
``make proto`` later replaces it with the standard protoc-generated module.
"""

from google.protobuf import descriptor_pb2 as _descriptor_pb2
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import message_factory as _message_factory
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper


def _field(message, name, number, field_type, *, type_name=""):
    field = message.field.add()
    field.name = name
    field.number = number
    field.label = _descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    field.type = field_type
    if type_name:
        field.type_name = type_name


_file = _descriptor_pb2.FileDescriptorProto()
_file.name = "messages.proto"
_file.package = "distsys.v1"
_file.syntax = "proto3"

_error_code = _file.enum_type.add()
_error_code.name = "ErrorCode"
for _name, _number in (
    ("ERROR_CODE_UNSPECIFIED", 0),
    ("UNKNOWN_TASK", 1),
    ("INVALID_REQUEST", 2),
    ("INTERNAL_ERROR", 3),
    ("TIMEOUT", 4),
):
    value = _error_code.value.add()
    value.name = _name
    value.number = _number

_envelope = _file.message_type.add()
_envelope.name = "Envelope"
_field(_envelope, "sender_id", 1, _descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
_field(_envelope, "correlation_id", 2, _descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
_field(_envelope, "timestamp_ms", 3, _descriptor_pb2.FieldDescriptorProto.TYPE_UINT64)
_field(_envelope, "ttl", 4, _descriptor_pb2.FieldDescriptorProto.TYPE_UINT32)
_field(_envelope, "payload", 5, _descriptor_pb2.FieldDescriptorProto.TYPE_BYTES)

_request = _file.message_type.add()
_request.name = "TaskRequest"
_field(_request, "task_name", 1, _descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
_field(_request, "payload_json", 2, _descriptor_pb2.FieldDescriptorProto.TYPE_BYTES)

_error = _file.message_type.add()
_error.name = "Error"
_field(
    _error,
    "code",
    1,
    _descriptor_pb2.FieldDescriptorProto.TYPE_ENUM,
    type_name=".distsys.v1.ErrorCode",
)
_field(_error, "message", 2, _descriptor_pb2.FieldDescriptorProto.TYPE_STRING)

_response = _file.message_type.add()
_response.name = "TaskResponse"
_field(_response, "success", 1, _descriptor_pb2.FieldDescriptorProto.TYPE_BOOL)
_field(_response, "result_json", 2, _descriptor_pb2.FieldDescriptorProto.TYPE_BYTES)
_field(
    _response,
    "error",
    3,
    _descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
    type_name=".distsys.v1.Error",
)
_field(_response, "processing_time_us", 4, _descriptor_pb2.FieldDescriptorProto.TYPE_UINT64)

DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(_file.SerializeToString())

ErrorCode = _enum_type_wrapper.EnumTypeWrapper(DESCRIPTOR.enum_types_by_name["ErrorCode"])
ERROR_CODE_UNSPECIFIED = 0
UNKNOWN_TASK = 1
INVALID_REQUEST = 2
INTERNAL_ERROR = 3
TIMEOUT = 4

Envelope = _message_factory.GetMessageClass(DESCRIPTOR.message_types_by_name["Envelope"])
TaskRequest = _message_factory.GetMessageClass(DESCRIPTOR.message_types_by_name["TaskRequest"])
Error = _message_factory.GetMessageClass(DESCRIPTOR.message_types_by_name["Error"])
TaskResponse = _message_factory.GetMessageClass(DESCRIPTOR.message_types_by_name["TaskResponse"])
