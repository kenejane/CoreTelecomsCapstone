
resource "aws_s3_bucket" "data_lake_s3_bucket" {
  bucket = "coretelecoms-capstone-data-lake"


  tags = {
    Name  = "CoreTelecomsCapstoneDataLakes3Bucket"
    Environment = "Production"
}
}

  resource "aws_s3_bucket_versioning" "data_lake_s3_bucket_versioning" {
  bucket = aws_s3_bucket.data_lake_s3_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
  }
