"""The teardown checks on small apply and destroy plans you can check by hand."""

from datetime import date

from conftest import mkplan, rc

from cloudcheck.teardown import check_teardown, ready

TAGS = {"app": "relay", "env": "nonprod"}


def deleted(type_, name, before):
    return rc(type_, name, None, actions=("delete",), before=before)


def test_complete_and_safe():
    applied = mkplan(rc("aws_vpc", "main", {"tags_all": TAGS}))
    destroy = mkplan(deleted("aws_vpc", "main", {"tags_all": TAGS}))
    found = check_teardown(applied, destroy, "nonprod")
    assert found == [] and ready(found)


def test_left_out_and_extra_actions():
    applied = mkplan(rc("aws_vpc", "main", {}), rc("aws_eip", "nat", {}))
    destroy = mkplan(deleted("aws_vpc", "main", {}), rc("aws_s3_bucket", "new", {}))
    assert [(f.rule, f.address, f.message) for f in check_teardown(applied, destroy, "nonprod")] == [
        ("TD001", "aws_eip.nat", "not deleted"), ("TD001", "aws_s3_bucket.new", "the destroy plan also creates it")]


def test_never_delete_what_belongs_to_someone_else():
    destroy = mkplan(deleted("aws_db_instance", "shared", {"tags_all": {"env": "shared"},
                                                           "final_snapshot_identifier": "s"}))
    found = check_teardown(mkplan(), destroy, "nonprod")
    assert [(f.rule, f.message) for f in found] == [("TD002", "would delete a resource tagged env=shared, app=-")]
    assert not ready(found)


def test_database_protection_and_final_snapshot():
    destroy = mkplan(deleted("aws_db_instance", "a", {"tags_all": TAGS, "deletion_protection": True,
                                                      "skip_final_snapshot": False, "final_snapshot_identifier": "f"}),
                     deleted("aws_db_instance", "b", {"tags_all": TAGS, "deletion_protection": False,
                                                      "skip_final_snapshot": True}))
    assert [(f.address, f.message) for f in check_teardown(mkplan(), destroy, "nonprod")] == [
        ("aws_db_instance.a", "destroy will fail: deletion protection is on"),
        ("aws_db_instance.b", "no final snapshot: the data is deleted with the database")]


def test_inventory_after_teardown():
    inv = {"ResourceTagMappingList": [
        {"ResourceARN": "arn:aws:rds:r:1:snapshot:final", "Tags": [{"Key": "env", "Value": "nonprod"},
                                                                    {"Key": "expires", "Value": "2027-01-04"}]},
        {"ResourceARN": "arn:aws:rds:r:1:snapshot:old", "Tags": [{"Key": "env", "Value": "nonprod"},
                                                                  {"Key": "expires", "Value": "2026-11-01"}]},
        {"ResourceARN": "arn:aws:rds:r:1:snapshot:undated", "Tags": [{"Key": "env", "Value": "nonprod"}]},
        {"ResourceARN": "arn:aws:ec2:r:1:volume/vol-1", "Tags": [{"Key": "env", "Value": "nonprod"}]},
        {"ResourceARN": "arn:aws:ec2:r:1:volume/vol-2", "Tags": [{"Key": "env", "Value": "prod"}]}]}
    found = check_teardown(mkplan(), mkplan(), "nonprod", inventory=inv, as_of=date(2026, 12, 1))
    assert [(f.address, f.message) for f in found] == [
        ("arn:aws:ec2:r:1:volume/vol-1", "left behind"),
        ("arn:aws:rds:r:1:snapshot:old", "retained past its expiry 2026-11-01"),
        ("arn:aws:rds:r:1:snapshot:undated", "retained with no expires tag")]
    assert ready(found)  # the inventory is judged after the destroy, not before it
