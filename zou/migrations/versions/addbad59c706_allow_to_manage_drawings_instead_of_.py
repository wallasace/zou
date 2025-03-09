"""allow to manage drawings instead of frames

Revision ID: addbad59c706
Revises: 20a8ad264659
Create Date: 2025-02-24 11:06:34.925091

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "addbad59c706"
down_revision = "06552e22f9e7"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("task", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("nb_drawings", sa.Integer(), nullable=True)
        )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("task", schema=None) as batch_op:
        batch_op.drop_column("nb_drawings")

    # ### end Alembic commands ###
