from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func  # ganz oben importieren
from datetime import datetime
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-me"  # nur für Flash-Messages

# SQLite-Datei – wird in einem Volume gemountet (/app/data)
db_path = os.environ.get("DB_PATH", "/app/data/shopping.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class ShoppingList(db.Model):
    __tablename__ = "shopping_lists"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    archived_at = db.Column(db.DateTime, nullable=True)
    active = db.Column(db.Boolean, default=True)

    items = db.relationship(
        "Item",
        backref="list",
        cascade="all, delete-orphan",
        lazy="joined",
    )


class Item(db.Model):
    __tablename__ = "items"

    id = db.Column(db.Integer, primary_key=True)
    list_id = db.Column(db.Integer, db.ForeignKey("shopping_lists.id"), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)  # <– neu: Integer
    done = db.Column(db.Boolean, default=False)



def init_db_if_needed():
    """
    Initialisiert SQLite sicher, indem geprüft wird,
    ob die Tabelle 'shopping_lists' existiert.
    Falls nicht → create_all().
    """
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    with app.app_context():
        try:
            # Test: Tabelle existiert?
            db.session.execute(db.select(ShoppingList)).first()
            app.logger.info("Datenbank bereits initialisiert.")
        except Exception as e:
            # Tabelle fehlt oder DB kaputt → neu erzeugen
            app.logger.warning(f"Datenbank nicht vollständig – initialisiere neu: {e}")
            db.create_all()
            app.logger.info("Datenbank-Tabellen wurden erstellt.")



@app.route("/")
def index():
    active_lists = (
        ShoppingList.query.filter_by(active=True)
        .order_by(ShoppingList.created_at.desc())
        .all()
    )
    archived_lists = (
        ShoppingList.query.filter_by(active=False)
        .order_by(ShoppingList.archived_at.desc())
        .all()
    )
    return render_template(
        "index.html",
        active_lists=active_lists,
        archived_lists=archived_lists,
    )

def rename_list(lst, new_name):
    """
    Benennt eine Einkaufsliste um.
    """
    if not new_name or not new_name.strip():
        raise ValueError("Neuer Name darf nicht leer sein.")
    lst.name = new_name.strip()
    db.session.commit()

@app.route("/lists", methods=["POST"])
def create_list():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Name der Einkaufsliste darf nicht leer sein.")
        return redirect(url_for("index"))

    lst = ShoppingList(name=name)
    db.session.add(lst)
    db.session.commit()
    return redirect(url_for("view_list", list_id=lst.id))


@app.route("/lists/<int:list_id>")
def view_list(list_id):
    lst = ShoppingList.query.get_or_404(list_id)
    return render_template("list.html", lst=lst)


@app.route("/lists/<int:list_id>/archive", methods=["POST"])
def archive_list(list_id):
    lst = ShoppingList.query.get_or_404(list_id)
    if not lst.active:
        flash("Liste ist bereits archiviert.")
    else:
        lst.active = False
        lst.archived_at = datetime.utcnow()
        db.session.commit()
        flash("Liste wurde archiviert.")
    return redirect(url_for("index"))

@app.route("/lists/<int:list_id>/activate", methods=["POST"])
def activate_list(list_id):
    lst = ShoppingList.query.get_or_404(list_id)

    if lst.active:
        flash("Liste ist bereits aktiv.")
        return redirect(url_for("index"))

    # Reaktivieren
    lst.active = True
    lst.archived_at = None

    # Automatische Umbenennung
    new_name = f"{lst.name} (reaktiviert am {datetime.utcnow().strftime('%d.%m.%Y')})"
    rename_list(lst, new_name)

    flash("Archivierte Einkaufsliste wurde reaktiviert und umbenannt.")
    return redirect(url_for("index"))

@app.route("/lists/<int:list_id>/rename", methods=["POST"])
def rename_list_route(list_id):
    lst = ShoppingList.query.get_or_404(list_id)
    new_name = request.form.get("new_name", "")

    try:
        rename_list(lst, new_name)
        flash("Einkaufsliste wurde umbenannt.")
    except ValueError as e:
        flash(str(e))

    return redirect(url_for("view_list", list_id=list_id))

@app.route("/lists/<int:list_id>/clone", methods=["POST"])
def clone_list(list_id):
    src = ShoppingList.query.get_or_404(list_id)
    new_name = f"{src.name} (Kopie)"

    new_list = ShoppingList(name=new_name, active=True)
    db.session.add(new_list)
    db.session.flush()  # damit new_list.id vorhanden ist

    for item in src.items:
        clone_item = Item(
            list_id=new_list.id,
            description=item.description,
            quantity=item.quantity,
            done=False,
        )
        db.session.add(clone_item)

    db.session.commit()
    flash("Neue Einkaufsliste aus Archivliste erstellt.")
    return redirect(url_for("view_list", list_id=new_list.id))


@app.route("/lists/<int:list_id>/items", methods=["POST"])
def add_item(list_id):
    lst = ShoppingList.query.get_or_404(list_id)
    if not lst.active:
        flash("Zu einer archivierten Liste können keine neuen Positionen hinzugefügt werden.")
        return redirect(url_for("view_list", list_id=list_id))

    description = request.form.get("description", "").strip()
    quantity_raw = (request.form.get("quantity") or "").strip()

    if not description:
        flash("Beschreibung darf nicht leer sein.")
        return redirect(url_for("view_list", list_id=list_id))

    # Menge interpretieren – default 1
    try:
        quantity = int(quantity_raw) if quantity_raw else 1
        if quantity <= 0:
            raise ValueError
    except ValueError:
        flash("Menge muss eine positive Zahl sein.")
        return redirect(url_for("view_list", list_id=list_id))

    item = Item(list_id=lst.id, description=description, quantity=quantity)
    db.session.add(item)
    db.session.commit()
    return redirect(url_for("view_list", list_id=list_id))

from sqlalchemy import func  # ganz oben importieren

@app.route("/lists/<int:list_id>/catalog")
def list_catalog(list_id):
    lst = ShoppingList.query.get_or_404(list_id)

    # Alle eindeutigen Artikel-Beschreibungen aus allen Listen
    all_descriptions = [
        row[0]
        for row in db.session.query(func.distinct(Item.description))
        .order_by(Item.description)
        .all()
    ]

    # Aktuelle Items dieser Liste als Map: description -> Item
    current_items_by_desc = {item.description: item for item in lst.items}

    # Katalog-Daten aufbereiten
    catalog = []
    for desc in all_descriptions:
        item = current_items_by_desc.get(desc)
        qty = item.quantity if item else 0
        catalog.append(
            {
                "description": desc,
                "quantity": qty,
            }
        )

    return render_template("catalog.html", lst=lst, catalog=catalog)

@app.route("/lists/<int:list_id>/catalog/update", methods=["POST"])
def list_catalog_update(list_id):
    lst = ShoppingList.query.get_or_404(list_id)

    if not lst.active:
        flash("Archivierte Listen können nicht geändert werden.")
        return redirect(url_for("list_catalog", list_id=list_id))

    description = (request.form.get("description") or "").strip()
    delta_raw = request.form.get("delta", "0")

    if not description:
        flash("Beschreibung fehlt.")
        return redirect(url_for("list_catalog", list_id=list_id))

    try:
        delta = int(delta_raw)
    except ValueError:
        flash("Ungültige Änderung der Menge.")
        return redirect(url_for("list_catalog", list_id=list_id))

    if delta == 0:
        return redirect(url_for("list_catalog", list_id=list_id))

    # Item der aktuellen Liste zu dieser Beschreibung suchen
    item = Item.query.filter_by(list_id=list_id, description=description).one_or_none()

    if item is None:
        # Noch nicht in dieser Liste vorhanden
        if delta > 0:
            # Neu mit Menge = delta (typisch 1)
            item = Item(list_id=list_id, description=description, quantity=delta)
            db.session.add(item)
    else:
        # Menge anpassen
        new_qty = (item.quantity or 0) + delta
        if new_qty <= 0:
            # Bei Menge 0 → löschen
            db.session.delete(item)
        else:
            item.quantity = new_qty

    db.session.commit()
    return redirect(url_for("list_catalog", list_id=list_id))



@app.route("/items/<int:item_id>/delete", methods=["POST"])
def delete_item(item_id):
    item = Item.query.get_or_404(item_id)
    list_id = item.list_id
    db.session.delete(item)
    db.session.commit()
    flash("Position gelöscht.")
    return redirect(url_for("view_list", list_id=list_id))


if __name__ == "__main__":
    # für lokales Testen
    init_db_if_needed()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    app.run(host="0.0.0.0", port=8080, debug=True)

