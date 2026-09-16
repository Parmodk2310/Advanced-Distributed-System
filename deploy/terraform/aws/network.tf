data "aws_availability_zones" "available" { state = "available" }

resource "aws_vpc" "this" {
  count                = var.enable_eks ? 1 : 0
  cidr_block           = "10.70.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
}
resource "aws_internet_gateway" "this" {
  count  = var.enable_eks ? 1 : 0
  vpc_id = aws_vpc.this[0].id
}
resource "aws_subnet" "public" {
  count                   = var.enable_eks ? 2 : 0
  vpc_id                  = aws_vpc.this[0].id
  cidr_block              = cidrsubnet(aws_vpc.this[0].cidr_block, 8, count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true
  tags = {
    "kubernetes.io/role/elb"              = "1"
    "kubernetes.io/cluster/${local.name}" = "shared"
  }
}
resource "aws_route_table" "public" {
  count  = var.enable_eks ? 1 : 0
  vpc_id = aws_vpc.this[0].id
}
resource "aws_route" "internet" {
  count                  = var.enable_eks ? 1 : 0
  route_table_id         = aws_route_table.public[0].id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this[0].id
}
resource "aws_route_table_association" "public" {
  count          = var.enable_eks ? 2 : 0
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public[0].id
}
