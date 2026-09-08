import random
import sys
import tkinter as tk
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path
from tkinter import messagebox, ttk


SUITS = ("clubs", "diamonds", "hearts", "spades")
RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "jack", "queen", "king", "ace")
CARD_VALUES = {str(value): value for value in range(2, 11)}
CARD_VALUES.update({"jack": 10, "queen": 10, "king": 10, "ace": 11})
DISPLAY_RANKS = {"jack": "J", "queen": "Q", "king": "K", "ace": "A"}


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    @property
    def filename(self) -> str:
        suffix = "2" if self.rank in {"jack", "queen", "king"} or self.suit == "spades" and self.rank == "ace" else ""
        return f"{self.rank}_of_{self.suit}{suffix}.png"


@dataclass
class Hand:
    cards: list[Card] = field(default_factory=list)
    stood: bool = False
    natural_eligible: bool = True

    def value(self) -> tuple[int, bool]:
        total = sum(CARD_VALUES[card.rank] for card in self.cards)
        aces = sum(card.rank == "ace" for card in self.cards)
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total, aces > 0

    def is_blackjack(self) -> bool:
        return self.natural_eligible and len(self.cards) == 2 and self.value()[0] == 21

    def is_bust(self) -> bool:
        return self.value()[0] > 21


@dataclass
class Player:
    name: str
    hand: Hand = field(default_factory=Hand)
    credits: float = 0
    bet: int = 0
    round_result: str = ""
    credit_change: float = 0
    hands: list[Hand] = field(default_factory=list)
    hand_bets: list[int] = field(default_factory=list)
    current_hand: int = 0

    def active_hand(self) -> Hand:
        return self.hands[self.current_hand]


class BlackjackApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Blackjack")
        self.root.geometry("1100x760")
        self.root.minsize(900, 700)
        self.root.configure(bg="#0b542d")
        self.asset_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "img"
        self.players: list[Player] = []
        self.dealer = Hand()
        self.deck: list[Card] = []
        self.current_player = 0
        self.round_over = False
        self.dealing = False
        self.deal_sequence: list[tuple[str, int | None]] = []
        self.deal_index = 0
        self.deal_effect: tuple[str, int | None] | None = None
        self.deal_card_frames: dict[tuple[int, ...], tk.Frame] = {}
        self.dealer_card_frames: list[tk.Frame] = []
        self.player_cards_frames: dict[tuple[int, int], tk.Frame] = {}
        self.player_boxes: list[tk.LabelFrame] = []
        self.hand_labels: dict[tuple[int, int], tk.Label] = {}
        self.hand_value_labels: dict[tuple[int, int], tk.Label] = {}
        self.hand_bet_labels: dict[tuple[int, int], tk.Label] = {}
        self.dealer_dealing = False
        self.dealer_reveal_pending = False
        self.images: dict[str, tk.PhotoImage] = {}
        self.show_setup()

    def show_setup(self) -> None:
        self.setup = tk.Toplevel(self.root)
        self.setup.title("Nuova partita")
        self.setup.resizable(False, False)
        self.setup.attributes("-topmost", True)
        self.setup.grab_set()
        frame = ttk.Frame(self.setup, padding=22)
        frame.grid()
        ttk.Label(frame, text="BLACKJACK", font=("Segoe UI", 22, "bold")).grid(columnspan=2, pady=(0, 14))
        ttk.Label(frame, text="Numero di giocatori (1-10):").grid(row=1, column=0, sticky="w", pady=5)
        self.count = tk.IntVar(value=1)
        self.count.trace_add("write", lambda *_args: self.update_names())
        count_box = ttk.Spinbox(frame, from_=1, to=10, textvariable=self.count, width=5, command=self.update_names)
        count_box.grid(row=1, column=1, sticky="e", pady=5)
        names_container = ttk.Frame(frame)
        names_container.grid(row=2, columnspan=2, sticky="ew", pady=(8, 4))
        self.name_canvas = tk.Canvas(names_container, height=190, highlightthickness=0)
        self.name_canvas.grid(row=0, column=0, sticky="ew")
        names_scrollbar = ttk.Scrollbar(names_container, orient="vertical", command=self.name_canvas.yview)
        names_scrollbar.grid(row=0, column=1, sticky="ns")
        self.name_canvas.configure(yscrollcommand=names_scrollbar.set)
        self.name_frame = ttk.Frame(self.name_canvas)
        self.name_window = self.name_canvas.create_window((0, 0), window=self.name_frame, anchor="nw")
        self.name_frame.bind("<Configure>", lambda _event: self.name_canvas.configure(scrollregion=self.name_canvas.bbox("all")))
        self.name_canvas.bind("<Configure>", lambda event: self.name_canvas.itemconfigure(self.name_window, width=event.width))
        names_container.columnconfigure(0, weight=1)
        self.name_vars: list[tk.StringVar] = []
        self.update_names()
        ttk.Label(frame, text="Crediti iniziali per giocatore:").grid(row=3, column=0, sticky="w", pady=5)
        self.credits_var = tk.StringVar(value="100")
        ttk.Entry(frame, textvariable=self.credits_var, width=8).grid(row=3, column=1, sticky="e", pady=5)
        ttk.Button(frame, text="Inizia partita", command=self.start_game).grid(row=4, columnspan=2, pady=(14, 0))
        self.setup.bind("<Return>", lambda _event: self.start_game())
        self.setup.update_idletasks()
        width = self.setup.winfo_width()
        height = self.setup.winfo_reqheight() + 24
        self.setup.minsize(width, height)
        screen_width = self.setup.winfo_screenwidth()
        screen_height = self.setup.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        self.setup.geometry(f"{width}x{height}+{x}+{y}")
        self.setup.lift()

    def update_names(self) -> None:
        if not hasattr(self, "name_frame"):
            return
        for child in self.name_frame.winfo_children():
            child.destroy()
        try:
            amount = max(1, min(10, int(self.count.get())))
        except (tk.TclError, ValueError):
            amount = 1
        old_values = [var.get() for var in self.name_vars]
        self.name_vars = []
        for index in range(amount):
            var = tk.StringVar(value=old_values[index] if index < len(old_values) else f"Giocatore {index + 1}")
            self.name_vars.append(var)
            ttk.Label(self.name_frame, text=f"Nome giocatore {index + 1}:").grid(row=index, column=0, sticky="w", pady=3)
            ttk.Entry(self.name_frame, textvariable=var, width=24).grid(row=index, column=1, padx=(10, 0), pady=3)
        self.name_canvas.itemconfigure(self.name_window, width=self.name_canvas.winfo_width())
        if hasattr(self, "credits_var"):
            self.setup.update_idletasks()
            width = max(self.setup.winfo_width(), self.setup.winfo_reqwidth())
            height = self.setup.winfo_reqheight() + 24
            screen_width = self.setup.winfo_screenwidth()
            screen_height = self.setup.winfo_screenheight()
            x = max(0, (screen_width - width) // 2)
            y = max(0, (screen_height - height) // 2)
            self.setup.geometry(f"{width}x{height}+{x}+{y}")

    def start_game(self) -> None:
        names = [var.get().strip() or f"Giocatore {index + 1}" for index, var in enumerate(self.name_vars)]
        try:
            credits = int(self.credits_var.get())
        except ValueError:
            messagebox.showerror("Crediti non validi", "Inserisci un numero intero di crediti positivo.", parent=self.setup)
            return
        if credits < 1:
            messagebox.showerror("Crediti non validi", "I crediti iniziali devono essere almeno 1.", parent=self.setup)
            return
        self.players = [Player(name, credits=credits) for name in names]
        self.setup.grab_release()
        self.setup.destroy()
        for widget_name in ("dealer_frame", "players_frame", "controls"):
            widget = getattr(self, widget_name, None)
            if widget is not None and widget.winfo_exists():
                widget.destroy()
        self.build_table()
        self.root.deiconify()
        self.root.state("zoomed")
        self.root.update_idletasks()
        self.root.after_idle(self.new_round)

    def build_table(self) -> None:
        self.dealer_frame = tk.LabelFrame(self.root, text="Dealer", bg="#0b542d", fg="white", font=("Segoe UI", 12, "bold"))
        self.dealer_frame.grid(row=0, column=0, sticky="ew", padx=18, pady=8)
        dealer_toolbar = tk.Frame(self.dealer_frame, bg="#0b542d")
        dealer_toolbar.pack(fill="x", padx=8, pady=(2, 0))
        self.new_game_button = tk.Button(dealer_toolbar, text="Nuova partita", command=self.show_setup)
        self.new_game_button.pack(side="right")
        self.dealer_cards = tk.Frame(self.dealer_frame, bg="#0b542d")
        self.dealer_cards.configure(width=240, height=175)
        self.dealer_cards.pack_propagate(False)
        self.dealer_cards.pack(pady=8)
        self.dealer_value_label = tk.Label(self.dealer_frame, text="", bg="#0b542d", fg="white", font=("Segoe UI", 10, "bold"))
        self.dealer_value_label.pack()
        self.players_frame = tk.Frame(self.root, bg="#0b542d")
        self.players_frame.grid(row=1, column=0, sticky="nsew", padx=18)
        for column in range(5):
            self.players_frame.columnconfigure(column, weight=1)
        self.players_frame.rowconfigure(0, weight=1)
        self.players_frame.rowconfigure(1, weight=1)
        self.controls = tk.Frame(self.root, bg="#083b22")
        self.controls.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        button_style = {"font": ("Segoe UI", 12, "bold"), "fg": "white", "activeforeground": "white"}
        self.hit_button = tk.Button(self.controls, text="CARTA (C)", width=12, bg="#178447", activebackground="#20a45b", command=self.hit, **button_style)
        self.hit_button.pack(side="left", padx=(18, 6), pady=12)
        self.stand_button = tk.Button(self.controls, text="STAI (S)", width=12, bg="#b56b13", activebackground="#d48a25", command=self.stand, **button_style)
        self.stand_button.pack(side="left", padx=6, pady=12)
        self.double_button = tk.Button(self.controls, text="RADDOPPIA (R)", width=12, bg="#7b4bb7", activebackground="#9866d2", command=self.double_down, **button_style)
        self.double_button.pack(side="left", padx=6, pady=12)
        self.split_button = tk.Button(self.controls, text="DIVIDI (D)", width=12, bg="#c04a78", activebackground="#dc668f", command=self.split_hand, **button_style)
        self.split_button.pack(side="left", padx=6, pady=12)
        self.next_button = tk.Button(self.controls, text="NUOVO GIRO (N)", width=15, bg="#1769aa", activebackground="#2d8fd5", command=self.new_round, state="disabled", **button_style)
        self.next_button.pack(side="right", padx=18, pady=12)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        self.root.bind_all("<KeyPress>", self.handle_key)

    def handle_key(self, event: tk.Event) -> str | None:
        if event.widget.winfo_toplevel() is not self.root:
            return None
        key = event.char.lower()
        actions = {
            "c": self.hit,
            "s": self.stand,
            "r": self.double_down,
            "d": self.split_hand,
        }
        if key in actions:
            actions[key]()
            return "break"
        if key == "n" and self.round_over:
            self.new_round()
            return "break"
        return None

    def new_round(self) -> None:
        self.players = [player for player in self.players if player.credits > 0]
        if not self.players:
            self.hit_button.config(state="disabled")
            self.stand_button.config(state="disabled")
            self.double_button.config(state="disabled")
            self.split_button.config(state="disabled")
            self.next_button.config(state="disabled")
            self.new_game_button.config(state="normal")
            self.show_setup()
            return
        if not self.collect_bets():
            return
        self.deck = [Card(rank, suit) for suit in SUITS for rank in RANKS]
        random.shuffle(self.deck)
        self.dealer = Hand()
        for player in self.players:
            player.hands = [Hand()]
            player.hand = player.hands[0]
            player.hand_bets = [player.bet]
            player.current_hand = 0
            player.round_result = ""
            player.credit_change = 0
        self.current_player = 0
        self.round_over = False
        self.dealing = True
        self.deal_sequence = []
        for _ in range(2):
            self.deal_sequence.extend(("player", index) for index in range(len(self.players)))
            self.deal_sequence.append(("dealer", None))
        self.deal_index = 0
        self.deal_effect = None
        self.hit_button.config(state="disabled")
        self.stand_button.config(state="disabled")
        self.double_button.config(state="disabled")
        self.split_button.config(state="disabled")
        self.next_button.config(state="disabled")
        self.render(hide_dealer=True, show_hand_values=False)
        self.root.after(500, self.deal_next_card)

    def deal_next_card(self) -> None:
        if not self.dealing or self.deal_index >= len(self.deal_sequence):
            return
        target, player_index = self.deal_sequence[self.deal_index]
        if target == "dealer":
            self.dealer.cards.append(self.deck.pop())
        else:
            self.players[player_index].hands[0].cards.append(self.deck.pop())
        self.deal_index += 1
        self.deal_effect = (target, player_index)
        self.render_deal_card(target, player_index)
        self.root.after(150, self.clear_deal_effect)
        if self.deal_index < len(self.deal_sequence):
            self.root.after(500, self.deal_next_card)
            return
        self.dealing = False
        self.deal_effect = None
        self.new_game_button.config(state="normal")
        self.render(hide_dealer=True, show_hand_values=True)
        self.advance_automatic_players()
        if not self.round_over:
            self.render(hide_dealer=True, show_hand_values=True)

    def clear_deal_effect(self) -> None:
        if self.deal_effect is None:
            return
        effect = self.deal_effect
        self.deal_effect = None
        if self.dealing or self.dealer_dealing:
            frames = self.dealer_card_frames if effect == ("dealer", None) else self.deal_card_frames.values()
            for frame in frames:
                frame.configure(highlightthickness=0)

    def render_deal_card(self, target: str, player_index: int | None) -> None:
        if target == "dealer":
            card = self.dealer.cards[-1]
            is_hidden = len(self.dealer.cards) == 2
            frame = tk.Frame(
                self.dealer_cards,
                width=108,
                height=165,
                bg="#173c2b" if is_hidden else "#0b542d",
                highlightthickness=2,
                highlightbackground="#f8d66d",
            )
            frame.grid_propagate(False)
            if is_hidden:
                tk.Label(frame, text="?", bg="#173c2b", fg="#f8d66d", font=("Segoe UI", 22, "bold")).place(relx=0.5, rely=0.5, anchor="center")
            else:
                tk.Label(frame, image=self.card_image(card, 5), bg="#0b542d").pack()
                tk.Label(frame, text=self.card_value_text(card), bg="#0b542d", fg="#f8d66d", font=("Segoe UI", 9, "bold")).pack()
            frame.grid(row=0, column=len(self.dealer_card_frames), padx=4)
            self.dealer_card_frames.append(frame)
            return
        assert player_index is not None
        self.add_player_card(player_index, 0, highlight=True)

    def add_player_card(self, player_index: int, hand_index: int, highlight: bool = False) -> None:
        hand = self.players[player_index].hands[hand_index]
        cards_frame = self.player_cards_frames[(player_index, hand_index)]
        card = hand.cards[-1]
        card_factor = 8
        card_frame = tk.Frame(
            cards_frame,
            bg="#0b542d",
            highlightthickness=2 if highlight else 0,
            highlightbackground="#f8d66d",
        )
        tk.Label(card_frame, image=self.card_image(card, card_factor), bg="#0b542d").pack()
        value_label = tk.Label(cards_frame, text=self.card_value_text(card), bg="#0b542d", fg="#f8d66d", font=("Segoe UI", 9, "bold"))
        self.position_player_card(cards_frame, card_frame, value_label, len(hand.cards) - 1)
        self.deal_card_frames[(player_index, hand_index, len(hand.cards) - 1)] = card_frame

    def position_player_card(
        self,
        cards_frame: tk.Frame,
        card_frame: tk.Frame,
        value_label: tk.Label,
        card_index: int,
    ) -> None:
        card_frame.update_idletasks()
        overlap_step = 28
        cards_frame.pack_propagate(False)
        card_width = card_frame.winfo_reqwidth()
        card_height = card_frame.winfo_reqheight()
        first_gap = 4
        if card_index == 0:
            x_position = 0
        elif card_index == 1:
            x_position = card_width + first_gap
        else:
            x_position = card_width + first_gap + overlap_step * (card_index - 1)
        cards_frame.configure(
            width=max(190, card_width * 2 + first_gap + overlap_step * max(0, card_index - 1)),
            height=card_height + 20,
        )
        card_frame.place(x=x_position, y=0)
        value_label.place(x=x_position + card_width // 2, y=card_height + 1, anchor="n")

    def collect_bets(self) -> bool:
        dialog = tk.Toplevel(self.root)
        dialog.title("Puntate")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.attributes("-topmost", True)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=18)
        frame.grid()
        ttk.Label(frame, text="Puntate del nuovo giro", font=("Segoe UI", 16, "bold")).grid(columnspan=3, pady=(0, 12))
        bet_vars: list[tk.StringVar] = []
        bet_entries: list[ttk.Entry] = []
        for index, player in enumerate(self.players):
            ttk.Label(frame, text=f"{player.name} - crediti: {player.credits}").grid(row=index + 1, column=0, sticky="w", pady=4)
            variable = tk.StringVar(value="1" if player.credits else "0")
            bet_vars.append(variable)
            entry = ttk.Entry(frame, textvariable=variable, width=10)
            entry.grid(row=index + 1, column=1, padx=12, pady=4)
            bet_entries.append(entry)
            ttk.Label(frame, text="(0 = salta il giro)" if player.credits == 0 else "crediti").grid(row=index + 1, column=2, sticky="w")
        error = ttk.Label(frame, text="", foreground="#b00020")
        error.grid(row=len(self.players) + 1, columnspan=3, pady=(8, 0))
        confirmed = False

        def confirm() -> None:
            nonlocal confirmed
            bets: list[int] = []
            for variable, player in zip(bet_vars, self.players):
                try:
                    bet = int(variable.get())
                except ValueError:
                    error.config(text="Inserisci solo numeri interi.")
                    return
                minimum = 1 if player.credits else 0
                if bet < minimum or bet > player.credits:
                    error.config(text="Ogni puntata deve essere tra 1 e i crediti disponibili.")
                    return
                bets.append(bet)
            if not any(bets):
                error.config(text="Almeno un giocatore deve partecipare al giro.")
                return
            for player, bet in zip(self.players, bets):
                player.bet = bet
                player.credits -= bet
            confirmed = True
            dialog.destroy()

        ttk.Button(frame, text="Conferma puntate", command=confirm).grid(row=len(self.players) + 2, columnspan=3, pady=(14, 0))
        def advance_bet(index: int, _event: tk.Event) -> str:
            if index == len(bet_entries) - 1:
                confirm()
            else:
                bet_entries[index + 1].focus_set()
                bet_entries[index + 1].selection_range(0, tk.END)
            return "break"

        for index, entry in enumerate(bet_entries):
            entry.bind("<Return>", lambda event, current=index: advance_bet(current, event))
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.lift()
        dialog.focus_force()
        if bet_entries:
            bet_entries[0].focus_set()
            bet_entries[0].selection_range(0, tk.END)
        self.root.wait_window(dialog)
        self.root.focus_force()
        return confirmed

    def advance_automatic_players(self) -> None:
        while self.current_player < len(self.players):
            player = self.players[self.current_player]
            while player.current_hand < len(player.hands):
                hand = player.active_hand()
                if player.hand_bets[player.current_hand] and not hand.stood and not hand.is_bust() and not hand.is_blackjack() and hand.value()[0] != 21:
                    self.update_action_buttons()
                    self.update_turn_visuals()
                    return
                player.current_hand += 1
            self.current_player += 1
        if self.current_player >= len(self.players):
            self.dealer_turn()
        else:
            self.update_turn_visuals()

    def update_turn_visuals(self) -> None:
        for index, box in enumerate(self.player_boxes):
            active = index == self.current_player and not self.round_over
            player = self.players[index]
            title = f"  TURNO DI {player.name.upper()}  " if active else f"  {player.name}  "
            background = "#145f38" if active else "#0b542d"
            box.configure(
                text=title,
                bg=background,
                bd=3 if active else 1,
                relief="solid" if active else "groove",
            )
        for (player_index, hand_index), label_widget in self.hand_labels.items():
            player = self.players[player_index]
            label = f"Mano {hand_index + 1}" if len(player.hands) > 1 else ""
            if player_index == self.current_player and hand_index == player.current_hand and not self.round_over:
                label += "  <- attiva"
            label_widget.configure(text=label)

    def update_hand_info(self, player_index: int, hand_index: int) -> None:
        hand = self.players[player_index].hands[hand_index]
        value = "sballato" if hand.is_bust() else str(hand.value()[0])
        suffix = "  (BLACKJACK)" if hand.is_blackjack() else ""
        self.hand_value_labels[(player_index, hand_index)].configure(text=f"Valore: {value}{suffix}")
        self.hand_bet_labels[(player_index, hand_index)].configure(
            text=f"Puntata: {self.players[player_index].hand_bets[hand_index]}"
        )

    def hit(self) -> None:
        if self.dealing or self.round_over or self.current_player >= len(self.players):
            return
        player_index = self.current_player
        hand_index = self.players[player_index].current_hand
        hand = self.players[player_index].active_hand()
        hand.cards.append(self.deck.pop())
        self.add_player_card(player_index, hand_index)
        self.update_hand_info(player_index, hand_index)
        if hand.is_bust() or hand.value()[0] == 21:
            hand.stood = True
            self.players[player_index].current_hand += 1
            self.advance_automatic_players()
        else:
            self.update_action_buttons()

    def double_down(self) -> None:
        if self.dealing or self.round_over or self.current_player >= len(self.players) or not self.can_double():
            return
        player = self.players[self.current_player]
        hand = player.active_hand()
        bet = player.hand_bets[player.current_hand]
        player.credits -= bet
        player.hand_bets[player.current_hand] *= 2
        player.bet += bet
        hand.cards.append(self.deck.pop())
        hand.stood = True
        self.add_player_card(self.current_player, player.current_hand)
        self.update_hand_info(self.current_player, player.current_hand)
        self.advance_automatic_players()

    def split_hand(self) -> None:
        if self.dealing or self.round_over or self.current_player >= len(self.players) or not self.can_split():
            return
        player = self.players[self.current_player]
        hand = player.active_hand()
        bet = player.hand_bets[player.current_hand]
        player.credits -= bet
        first, second = hand.cards
        first_hand = Hand(cards=[first], natural_eligible=False)
        second_hand = Hand(cards=[second], natural_eligible=False)
        player.hands[player.current_hand:player.current_hand + 1] = [first_hand, second_hand]
        player.hand_bets[player.current_hand:player.current_hand + 1] = [bet, bet]
        player.bet += bet
        first_hand.cards.append(self.deck.pop())
        second_hand.cards.append(self.deck.pop())
        if first.rank == "ace":
            first_hand.stood = True
            second_hand.stood = True
        self.advance_automatic_players()
        if not self.round_over:
            self.render(hide_dealer=True)

    def stand(self) -> None:
        if self.dealing or self.round_over or self.current_player >= len(self.players):
            return
        self.players[self.current_player].active_hand().stood = True
        self.players[self.current_player].current_hand += 1
        self.advance_automatic_players()

    def dealer_turn(self) -> None:
        self.dealer_dealing = True
        self.dealer_reveal_pending = True
        self.hit_button.config(state="disabled")
        self.stand_button.config(state="disabled")
        self.double_button.config(state="disabled")
        self.split_button.config(state="disabled")
        self.root.after(500, self.deal_dealer_card)

    def deal_dealer_card(self) -> None:
        if not self.dealer_dealing:
            return
        if self.dealer_reveal_pending:
            self.dealer_reveal_pending = False
            self.render(hide_dealer=False)
            self.root.after(500, self.deal_dealer_card)
            return
        if self.dealer.value()[0] < 17:
            self.dealer.cards.append(self.deck.pop())
            self.deal_effect = ("dealer", None)
            self.render_deal_card("dealer", None)
            self.dealer_value_label.config(text=f"Valore: {self.dealer.value()[0]}")
            self.root.after(150, self.clear_deal_effect)
            self.root.after(500, self.deal_dealer_card)
            return
        self.dealer_dealing = False
        self.round_over = True
        self.next_button.config(state="normal")
        self.results_text()
        self.render(hide_dealer=False)

    def results_text(self) -> str:
        dealer_value = self.dealer.value()[0]
        results = []
        for player in self.players:
            credits_before_result = player.credits + sum(player.hand_bets)
            hand_results = []
            for hand, bet in zip(player.hands, player.hand_bets):
                value = hand.value()[0]
                if bet == 0:
                    result = "salta"
                elif hand.is_bust():
                    result = "sballato"
                elif self.dealer.is_blackjack():
                    result = "pareggio" if hand.is_blackjack() else "perde"
                elif hand.is_blackjack() and not self.dealer.is_blackjack():
                    result = "BLACKJACK!"
                elif self.dealer.is_bust():
                    result = "vince"
                elif value > dealer_value:
                    result = "vince"
                elif value == dealer_value:
                    result = "pareggio"
                else:
                    result = "perde"
                if result == "BLACKJACK!":
                    player.credits += ceil(bet * 2.5)
                elif result == "vince":
                    player.credits += ceil(bet * 2)
                elif result == "pareggio":
                    player.credits += ceil(bet)
                hand_results.append(result)
            player.credit_change = player.credits - credits_before_result
            player.round_result = " / ".join(hand_results)
            results.append(f"{player.name}: {player.round_result}")
        return f"Dealer: {dealer_value if not self.dealer.is_bust() else 'sballato'}  |  " + "  •  ".join(results)

    def can_double(self) -> bool:
        if self.round_over or self.current_player >= len(self.players):
            return False
        player = self.players[self.current_player]
        hand = player.active_hand()
        return len(hand.cards) == 2 and player.credits >= player.hand_bets[player.current_hand]

    def can_split(self) -> bool:
        if self.round_over or self.current_player >= len(self.players):
            return False
        player = self.players[self.current_player]
        hand = player.active_hand()
        return (
            len(player.hands) < 2
            and len(hand.cards) == 2
            and hand.cards[0].rank == hand.cards[1].rank
            and player.credits >= player.hand_bets[player.current_hand]
        )

    def update_action_buttons(self) -> None:
        if self.round_over or self.current_player >= len(self.players):
            self.hit_button.config(state="disabled")
            self.stand_button.config(state="disabled")
            self.double_button.config(state="disabled")
            self.split_button.config(state="disabled")
            return
        self.hit_button.config(state="normal")
        self.stand_button.config(state="normal")
        self.double_button.config(state="normal" if self.can_double() else "disabled")
        self.split_button.config(state="normal" if self.can_split() else "disabled")

    def card_image(self, card: Card, factor: int) -> tk.PhotoImage:
        cache_key = f"{card.filename}:{factor}"
        if cache_key not in self.images:
            image = tk.PhotoImage(file=str(self.asset_dir / card.filename))
            self.images[cache_key] = image.subsample(factor, factor)
        return self.images[cache_key]

    def card_value_text(self, card: Card) -> str:
        if card.rank == "ace":
            return "1/11"
        return str(CARD_VALUES[card.rank])

    def render(self, hide_dealer: bool, show_hand_values: bool = True) -> None:
        self.deal_card_frames = {}
        self.dealer_card_frames = []
        self.player_cards_frames = {}
        self.player_boxes = []
        self.hand_labels = {}
        self.hand_value_labels = {}
        self.hand_bet_labels = {}
        for widget in self.dealer_cards.winfo_children():
            widget.destroy()
        for index, card in enumerate(self.dealer.cards):
            is_effect_card = self.deal_effect == ("dealer", None) and index == len(self.dealer.cards) - 1
            if hide_dealer and index == 1:
                label = tk.Frame(
                    self.dealer_cards,
                    width=108,
                    height=165,
                    bg="#173c2b",
                    highlightthickness=2 if is_effect_card else 1,
                    highlightbackground="#f8d66d",
                )
                label.grid_propagate(False)
                tk.Label(label, text="?", bg="#173c2b", fg="#f8d66d", font=("Segoe UI", 22, "bold")).place(relx=0.5, rely=0.5, anchor="center")
            else:
                label = tk.Frame(
                    self.dealer_cards,
                    width=108,
                    height=165,
                    bg="#0b542d",
                    highlightthickness=2 if is_effect_card else 0,
                    highlightbackground="#f8d66d",
                )
                label.grid_propagate(False)
                tk.Label(label, image=self.card_image(card, 5), bg="#0b542d").pack()
                tk.Label(label, text=self.card_value_text(card), bg="#0b542d", fg="#f8d66d", font=("Segoe UI", 9, "bold")).pack()
            label.grid(row=0, column=index, padx=4)
        shown_value = "?" if hide_dealer else ("sballato" if self.dealer.is_bust() else str(self.dealer.value()[0]))
        self.dealer_value_label.config(text=f"Valore: {shown_value}")
        for widget in self.players_frame.winfo_children():
            widget.destroy()
        for index, player in enumerate(self.players):
            active = index == self.current_player and not self.round_over
            background = "#145f38" if active else "#0b542d"
            title = f"  TURNO DI {player.name.upper()}  " if active else f"  {player.name}  "
            box = tk.LabelFrame(self.players_frame, text=title, bg=background, fg="#f8d66d", bd=3 if active else 1, relief="solid" if active else "groove", font=("Segoe UI", 12, "bold"))
            columns = min(5, len(self.players))
            rows = ceil(len(self.players) / columns)
            box_width = max(160, (self.root.winfo_width() - 36 - (columns - 1) * 10) // columns)
            box_height = max(180, (self.root.winfo_height() - 300) // rows)
            box.configure(width=box_width, height=box_height)
            box.grid_propagate(False)
            box.grid(row=index // columns, column=index % columns, sticky="nsew", padx=5, pady=4)
            self.player_boxes.append(box)
            box.columnconfigure(0, weight=1)
            box.columnconfigure(1, weight=0)
            box.rowconfigure(0, weight=1)
            info_frame = tk.Frame(box, bg=background)
            info_frame.grid(row=0, column=0, sticky="nsew", padx=(5, 2), pady=6)
            tk.Label(
                info_frame,
                text=f"Crediti: {player.credits:g}\nPuntata totale: {player.bet}",
                bg=background,
                fg="white",
                justify="left",
                anchor="nw",
                font=("Segoe UI", 9, "bold"),
            ).pack(anchor="nw")
            hands_frame = tk.Frame(box, bg=background)
            hands_frame.configure(width=190)
            hands_frame.grid_propagate(False)
            hands_frame.grid(row=0, column=1, sticky="ne", padx=(2, 5), pady=4)
            for hand_index, hand in enumerate(player.hands):
                hand_frame = tk.Frame(hands_frame, bg=background)
                hand_frame.pack(anchor="e", pady=(2, 5))
                label = f"Mano {hand_index + 1}" if len(player.hands) > 1 else ""
                if hand_index == player.current_hand and active:
                    label += "  <- attiva"
                value = "sballato" if hand.is_bust() else str(hand.value()[0])
                suffix = "  (BLACKJACK)" if hand.is_blackjack() else ""
                cards = tk.Frame(hand_frame, bg=background)
                cards.pack(anchor="e")
                self.player_cards_frames[(index, hand_index)] = cards
                card_factor = 8
                for card_index, card in enumerate(hand.cards):
                    is_effect_card = (
                        self.deal_effect == ("player", index)
                        and hand_index == 0
                        and card is hand.cards[-1]
                    )
                    card_frame = tk.Frame(
                        cards,
                        bg=background,
                        highlightthickness=2 if is_effect_card else 0,
                        highlightbackground="#f8d66d",
                    )
                    tk.Label(card_frame, image=self.card_image(card, card_factor), bg=background).pack()
                    value_label = tk.Label(cards, text=self.card_value_text(card), bg=background, fg="#f8d66d", font=("Segoe UI", 9, "bold"))
                    self.position_player_card(cards, card_frame, value_label, card_index)
                hand_data = tk.Frame(info_frame, bg="#104a2d")
                hand_data.pack(anchor="nw", pady=(8 if hand_index == 0 else 5, 0))
                hand_label = tk.Label(hand_data, text=label if show_hand_values else "", bg="#104a2d", fg="#f8d66d", font=("Segoe UI", 9, "bold"), justify="left")
                hand_label.pack(anchor="w")
                self.hand_labels[(index, hand_index)] = hand_label
                if show_hand_values:
                    value_label = tk.Label(hand_data, text=f"Valore: {value}{suffix}", bg="#104a2d", fg="white", font=("Segoe UI", 8, "bold"), justify="left")
                    value_label.pack(anchor="w")
                    bet_label = tk.Label(hand_data, text=f"Puntata: {player.hand_bets[hand_index]}", bg="#104a2d", fg="#f8d66d", font=("Segoe UI", 8, "bold"))
                    bet_label.pack(anchor="w")
                    self.hand_value_labels[(index, hand_index)] = value_label
                    self.hand_bet_labels[(index, hand_index)] = bet_label
            if self.round_over and player.round_result:
                result_color = "#7dff9b" if "vince" in player.round_result else "#ff8585" if "perde" in player.round_result or "sballato" in player.round_result else "#f8d66d"
                tk.Label(
                    info_frame,
                    text=f"Esito: {player.round_result} ({player.credit_change:+g} crediti)",
                    bg=background,
                    fg=result_color,
                    font=("Segoe UI", 8, "bold"),
                    wraplength=max(90, box_width // 2),
                    justify="left",
                    anchor="sw",
                ).pack(side="bottom", anchor="sw")
        self.update_action_buttons()


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    BlackjackApp(root)
    root.deiconify()
    root.mainloop()
