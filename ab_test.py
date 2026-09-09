import os
import json
from datetime import datetime

class ABTest:
    """
    A/B Testing for trading strategy parameters.
    
    Variant A: Trailing stop (default) - ride winners
    Variant B: Fixed 1.5% target - take profits quickly
    
    Bot randomly assigns each trade to A or B.
    After 20 trades we compare win rates and avg P&L.
    """

    VARIANTS = {
        'A': {
            'name': 'Trailing stop',
            'description': 'No fixed target, trail 0.3% below peak',
            'use_trailing': True,
            'profit_target': None,
            'stop_loss': 0.005,
            'trail_pct': 0.003,
            'min_score': 7
        },
        'B': {
            'name': 'Fixed 1.5% target',
            'description': 'Exit at exactly 1.5% profit',
            'use_trailing': False,
            'profit_target': 0.015,
            'stop_loss': 0.005,
            'trail_pct': None,
            'min_score': 7
        }
    }

    def __init__(self):
        self.log_file = 'ab_test_results.json'
        self.results = self.load_results()
        self.trade_count = sum(len(v['trades']) for v in self.results.values())

    def load_results(self):
        try:
            with open(self.log_file) as f:
                return json.load(f)
        except:
            return {
                'A': {'trades': [], 'total_pnl': 0, 'wins': 0, 'losses': 0},
                'B': {'trades': [], 'total_pnl': 0, 'wins': 0, 'losses': 0}
            }

    def save_results(self):
        with open(self.log_file, 'w') as f:
            json.dump(self.results, f, indent=2)

    def get_variant_for_trade(self):
        """Alternate A/B for each trade."""
        return 'A' if self.trade_count % 2 == 0 else 'B'

    def get_params(self, variant):
        return self.VARIANTS[variant]

    def log_trade(self, variant, trade):
        self.results[variant]['trades'].append(trade)
        self.results[variant]['total_pnl'] += trade['pnl']
        if trade['pnl'] > 0:
            self.results[variant]['wins'] += 1
        else:
            self.results[variant]['losses'] += 1
        self.trade_count += 1
        self.save_results()

    def get_report(self):
        report = "\n=== A/B TEST RESULTS ===\n"
        for v, data in self.results.items():
            total = data['wins'] + data['losses']
            wr = (data['wins']/total*100) if total > 0 else 0
            avg_pnl = data['total_pnl']/total if total > 0 else 0
            params = self.VARIANTS[v]
            report += "\nVariant {} - {}:\n".format(v, params['name'])
            report += "  Trades: {} | Wins: {} | Losses: {}\n".format(
                total, data['wins'], data['losses'])
            report += "  Win rate: {:.1f}%\n".format(wr)
            report += "  Total P&L: Rs.{:.2f}\n".format(data['total_pnl'])
            report += "  Avg P&L: Rs.{:.2f}\n".format(avg_pnl)

        a = self.results['A']
        b = self.results['B']
        a_total = a['wins'] + a['losses']
        b_total = b['wins'] + b['losses']
        if a_total > 0 and b_total > 0:
            a_avg = a['total_pnl'] / a_total
            b_avg = b['total_pnl'] / b_total
            winner = 'A (Trailing)' if a_avg > b_avg else 'B (Fixed target)'
            report += "\nWINNER SO FAR: {}\n".format(winner)
            report += "Need 20+ trades per variant for statistical significance.\n"
        report += "========================\n"
        return report
